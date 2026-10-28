create table if not exists public.shipping_time_cidade_diario (
  data date not null,
  codigo_base bigint not null,
  base text not null default '',
  cidade_base text not null default '',
  cidade_destino text not null,
  rm text not null default '',
  sc text not null default '',
  etapa_8_h double precision not null default 0,
  pacotes integer not null default 0,
  updated_at timestamptz not null default now(),
  primary key (data, codigo_base, cidade_destino)
);

create index if not exists idx_shipping_time_cidade_data
  on public.shipping_time_cidade_diario (data);

create index if not exists idx_shipping_time_cidade_base
  on public.shipping_time_cidade_diario (codigo_base);

create index if not exists idx_shipping_time_cidade_destino
  on public.shipping_time_cidade_diario (cidade_destino);

alter table public.shipping_time_cidade_diario enable row level security;

-- A aplicação usa chave secret/service role no backend, então não é necessário
-- liberar leitura pública para anon/authenticated.
