J&T - SHIPPING TIME DASHBOARD

PADRÃO IGUAL AOS DASHBOARDS SLA/CAPOTAMENTO:
1) Excel é importado pelo terminal usando importar_excel.py
2) O importador filtra somente as bases do R/M Orlean
3) Cruza Código da base de entrega com Estação No. da Gestão
4) S/C = Supervisor; se Supervisor estiver vazio, usa Coordenador
5) Grava o resultado no Supabase
6) main.py/FastAPI apenas consulta o banco e serve o dashboard

PASTA DE TRABALHO NO WINDOWS
C:\Users\JT074\Documents\Dashboard\Shipping Time

PRIMEIRO USO
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

Preencha .env com SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY.
Execute schema.sql no SQL Editor do Supabase uma vez.

VALIDAR UM ARQUIVO SEM ENVIAR AO BANCO
python importar_excel.py "全网时效分析(新)-Lista33620020261022153046.xlsx" "Gestão de colaboradores(4).xlsx" --dry-run

IMPORTAR DE VERDADE
python importar_excel.py "全网时效分析(新)-Lista33620020261022153046.xlsx" "Gestão de colaboradores(4).xlsx"

SUBIR O DASHBOARD
python -m uvicorn main:app --reload --port 8002

ABRIR
http://127.0.0.1:8002

COLUNAS USADAS
AG = Código da base de entrega
AM = Tempo trânsito SC Destino->Base Entrega (Etapa 6)
AP = Tempo médio processamento Base Entrega (Etapa 7)
AQ = Tempo médio Saída para Entrega->Entrega (Etapa 8)

REGRA DE CÁLCULO
Etapa 6 = SOMA(AM) / total de pacotes
Etapa 7 = SOMA(AP) / total de pacotes
Etapa 8 = SOMA(AQ) / total de pacotes
Shipping 6+7+8 = (SOMA(AM)+SOMA(AP)+SOMA(AQ)) / total de pacotes
Campos vazios entram como zero no somatório e o pacote permanece no denominador.
