ATUALIZAÇÕES V8

- Cabeçalho mantido apenas com "Shipping Time" e "Performance Last Mile"
- Adicionado filtro de CIDADE
- Tabelas de piores bases agora mostram: BASE | CIDADE | S/C | HORAS | PACOTES
- Painéis E6/E7/E8 ficam um abaixo do outro
- Importador aceita arquivo "Segundo Segmento.xlsx" para mapear cidade por código da base

COMO IMPORTAR

1) Atualize o schema no Supabase executando o schema.sql
2) Coloque na pasta:
   - arquivo Shipping Time
   - Gestão de colaboradores.xlsx
   - Segundo Segmento.xlsx
3) Rode:
   python importar_excel.py "SEU_ARQUIVO_SHIPPING.xlsx" "Gestão de colaboradores.xlsx" --dry-run

Se o arquivo Segundo Segmento.xlsx estiver na mesma pasta, ele será usado automaticamente.
