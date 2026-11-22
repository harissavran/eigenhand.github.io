-- =====================================================================
-- EIGENHAND PROPERTY LOCATOR - Datenbankschema
--
-- Einmalig im Supabase SQL Editor ausfuehren (Dashboard > SQL Editor >
-- New query > einfuegen > Run). Das Skript ist wiederholbar: es legt
-- nichts doppelt an und loescht keine bestehenden Daten.
--
-- Datenquelle der GWR-Tabellen: Eidg. Gebaeude- und Wohnungsregister,
-- Bundesamt fuer Statistik, oeffentliche Daten der Berechtigungsstufe A
-- (https://www.housing-stat.ch/de/madd/public.html). Quellenangabe ist
-- gemaess Nutzungsbedingungen Pflicht und steht im Cockpit unter
-- "Verwendete Datenquellen".
-- =====================================================================


-- ---------------------------------------------------------------------
-- 1. Analysierte Inserate
-- ---------------------------------------------------------------------
create table if not exists public.locator_objekte (
  id                 uuid primary key default gen_random_uuid(),
  created_at         timestamptz not null default now(),
  analysiert_at      timestamptz not null default now(),

  -- Inserat
  portal             text,
  inserat_id         text,
  url                text,
  makler             text,

  -- Ort
  gemeinde           text,
  plz                text,
  quartier           text,

  -- Objekt
  objektart          text,
  zimmer             numeric(4,1),
  wohnflaeche        numeric(8,1),
  grundstueck        numeric(10,1),
  baujahr            smallint,
  etage              text,
  stockwerke         smallint,
  balkon             boolean not null default false,
  terrasse           boolean not null default false,
  garten             boolean not null default false,
  garage             boolean not null default false,
  parkplaetze        text,
  preis              numeric(12,2),
  beschreibung       text,

  -- Standort, nur bei zulaessiger Quelle gefuellt
  adresse            text,
  egid               bigint,
  grundstuecksnummer text,

  status             text not null default 'nicht_verifizierbar'
                     check (status in ('bestaetigt','nicht_eindeutig','nicht_verifizierbar')),

  kandidaten         jsonb not null default '[]'::jsonb,  -- moegliche Treffer, nie als bestaetigt
  quellen            jsonb not null default '[]'::jsonb,  -- Rueckverfolgbarkeit je Analyse
  manuell            jsonb not null default '{}'::jsonb   -- vom Nutzer geaenderte Felder
);

comment on table public.locator_objekte is
  'Analysierte Immobilieninserate. Enthaelt keine Eigentuemerdaten.';
comment on column public.locator_objekte.adresse is
  'Nur ausgefuellt, wenn die Adresse amtlich aufgeloest wurde (Status bestaetigt).';

-- Doppelte Inserate verhindern: gleiche Inseratsnummer je Portal, bzw. gleicher Link
create unique index if not exists locator_uq_inserat
  on public.locator_objekte (portal, inserat_id)
  where inserat_id is not null and inserat_id <> '';

create unique index if not exists locator_uq_url
  on public.locator_objekte (url)
  where url is not null and url <> '';

create index if not exists locator_idx_ort on public.locator_objekte (plz, gemeinde);

alter table public.locator_objekte enable row level security;
drop policy if exists locator_objekte_auth on public.locator_objekte;
create policy locator_objekte_auth on public.locator_objekte
  for all to authenticated using (true) with check (true);


-- ---------------------------------------------------------------------
-- 2. GWR-Gebaeude (Import via tools/locator_import_gwr.py)
-- ---------------------------------------------------------------------
create table if not exists public.gwr_gebaeude (
  egid     bigint primary key,
  gdenr    integer,            -- BFS-Gemeindenummer
  gdename  text,               -- Gemeindename
  plz4     integer,
  plzname  text,
  strname  text,               -- Strassenbezeichnung
  deinr    text,               -- Eingangsnummer / Hausnummer
  gkode    double precision,   -- E-Koordinate LV95
  gkodn    double precision,   -- N-Koordinate LV95
  gbauj    smallint,           -- Baujahr
  gbaup    smallint,           -- Bauperiode, falls Baujahr fehlt
  gastw    smallint,           -- Anzahl Geschosse
  garea    integer,            -- Gebaeudefläche m2
  ganzwhg  smallint,           -- Anzahl Wohnungen
  gkat     smallint,           -- Gebaeudekategorie
  gklas    smallint            -- Gebaeudeklasse
);

create index if not exists gwr_geb_plz_bauj on public.gwr_gebaeude (plz4, gbauj);
create index if not exists gwr_geb_gde      on public.gwr_gebaeude (lower(gdename));
create index if not exists gwr_geb_plzname  on public.gwr_gebaeude (lower(plzname));

alter table public.gwr_gebaeude enable row level security;
drop policy if exists gwr_gebaeude_read on public.gwr_gebaeude;
create policy gwr_gebaeude_read on public.gwr_gebaeude
  for select to authenticated using (true);


-- ---------------------------------------------------------------------
-- 3. GWR-Wohnungen
--    Wird nur gefuellt, wenn der oeffentliche Export Wohnungsdaten
--    enthaelt. Das Importskript sagt, ob das der Fall ist.
-- ---------------------------------------------------------------------
create table if not exists public.gwr_wohnung (
  egid   bigint   not null,
  ewid   integer  not null,
  wstwk  smallint,            -- Stockwerk
  wazim  numeric(4,1),        -- Anzahl Zimmer
  warea  integer,             -- Wohnungsfläche m2
  wmehrg smallint,            -- mehrgeschossige Wohnung (Duplex)
  primary key (egid, ewid)
);

create index if not exists gwr_whg_zim_area on public.gwr_wohnung (wazim, warea);
create index if not exists gwr_whg_egid     on public.gwr_wohnung (egid);

alter table public.gwr_wohnung enable row level security;
drop policy if exists gwr_wohnung_read on public.gwr_wohnung;
create policy gwr_wohnung_read on public.gwr_wohnung
  for select to authenticated using (true);


-- ---------------------------------------------------------------------
-- 4. Kandidatensuche
--
--    Liefert Gebaeude, die in den uebergebenen Merkmalen mit dem Inserat
--    uebereinstimmen. Ein Treffer ist ein Kandidat, keine Bestaetigung.
--    Baujahr wird mit +/- 1 Jahr gesucht (Bezugs- vs. Baujahr weichen oft
--    ab), die Flaeche mit der uebergebenen Toleranz, weil die
--    GWR-Wohnungsflaeche anders definiert ist als die Inseratsangabe.
--
--    Sind keine Wohnungsdaten importiert, wird nur auf Gebaeudeebene
--    gefiltert und das Feld "treffer" sagt das offen.
-- ---------------------------------------------------------------------
create or replace function public.locator_kandidaten(
  p_gemeinde text    default null,
  p_plz      integer default null,
  p_baujahr  integer default null,
  p_zimmer   numeric default null,
  p_flaeche  numeric default null,
  p_tol      numeric default 0.10
)
returns table (
  egid    bigint,
  adresse text,
  strname text,
  deinr   text,
  plz4    integer,
  plzname text,
  gdename text,
  gbauj   smallint,
  gastw   smallint,
  garea   integer,
  ganzwhg smallint,
  gkode   double precision,
  gkodn   double precision,
  wazim   numeric,
  warea   integer,
  wstwk   smallint,
  treffer text
)
language plpgsql
stable
security invoker
set search_path = public
as $$
declare
  v_hat_whg  boolean;
  v_use_whg  boolean;
  v_kriterien text;
begin
  if p_gemeinde is null and p_plz is null then
    raise exception 'Mindestens Gemeinde oder PLZ wird benötigt';
  end if;

  select exists (select 1 from public.gwr_wohnung limit 1) into v_hat_whg;
  v_use_whg := v_hat_whg and (p_zimmer is not null or p_flaeche is not null);

  v_kriterien := nullif(concat_ws(', ',
      case when p_plz is not null or p_gemeinde is not null then 'Ort' end,
      case when p_baujahr is not null then 'Baujahr ±1' end,
      case when v_use_whg and p_zimmer  is not null then 'Zimmer' end,
      case when v_use_whg and p_flaeche is not null then 'Fläche ±'||round(p_tol*100)||'%' end
    ), '');

  if not v_use_whg and (p_zimmer is not null or p_flaeche is not null) then
    v_kriterien := v_kriterien || ' (keine Wohnungsdaten importiert, nur Gebäudeebene)';
  end if;

  return query
  with geb as (
    select g.*
      from public.gwr_gebaeude g
     where (p_plz is null or g.plz4 = p_plz)
       and (p_gemeinde is null
            or lower(g.gdename) = lower(p_gemeinde)
            or lower(g.plzname) = lower(p_gemeinde))
       and (p_baujahr is null
            or g.gbauj between p_baujahr - 1 and p_baujahr + 1)
  )
  select g.egid,
         nullif(trim(concat_ws(' ', g.strname, g.deinr)), '') as adresse,
         g.strname, g.deinr, g.plz4, g.plzname, g.gdename,
         g.gbauj, g.gastw, g.garea, g.ganzwhg, g.gkode, g.gkodn,
         w.wazim, w.warea, w.wstwk,
         v_kriterien as treffer
    from geb g
    left join public.gwr_wohnung w
           on v_use_whg
          and w.egid = g.egid
          and (p_zimmer  is null or w.wazim = p_zimmer)
          and (p_flaeche is null or w.warea between p_flaeche * (1 - p_tol)
                                               and p_flaeche * (1 + p_tol))
   where not v_use_whg or w.egid is not null
   order by g.plz4, g.strname nulls last, g.deinr nulls last
   limit 200;
end;
$$;

grant execute on function public.locator_kandidaten(text,integer,integer,numeric,numeric,numeric)
  to authenticated;

-- Kurzer Funktionstest (liefert 0 Zeilen, solange nichts importiert ist):
-- select * from public.locator_kandidaten('Niederglatt', 8172, 2006, 5.5, 151, 0.10);
