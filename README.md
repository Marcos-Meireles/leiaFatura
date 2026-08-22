# 🧾 Divisor de Fatura

Aplicativo web em [Streamlit](https://streamlit.io/) para importar a fatura do cartão de crédito Nubank (CSV), classificar cada compra e dividir os valores entre você e outras pessoas — com histórico de classificações e exportação para Excel.

## Funcionalidades

- **Upload da fatura Nubank em CSV** — importa o extrato exportado direto do app do Nubank.
- **Identificação por usuário** — cada pessoa usa seu próprio nome, e os dados ficam salvos em um banco SQLite separado (`fatura_<usuario>.db`).
- **Agrupamento de parcelas** — compras parceladas (ex: "Amazon - Parcela 3/6") são reconhecidas e agrupadas pela descrição base.
- **Classificação por transação** — para cada compra, defina uma categoria (ex: transporte, mercado) e com quem ela deve ser dividida.
- **Histórico de classificações** — categorias e divisões já usadas são sugeridas automaticamente da próxima vez que a mesma despesa aparecer, e podem ser limpas a qualquer momento.
- **Tratamento automático de**:
  - Pagamentos de fatura (ignorados no cálculo).
  - Estornos/reembolsos (reduzem o total líquido devido).
- **Resumo financeiro** — total de compras, estornos, total líquido, sua parte e quanto cada pessoa te deve.
- **Detalhamento por pessoa** — lista de despesas de cada participante.
- **Exportação para Excel** — gera uma planilha `.xlsx` com abas: fatura dividida completa, "O que me devem" e uma aba por pessoa.

## Instalação

```bash
pip install -r requirements.txt
```

## Como executar

```bash
streamlit run app.py
```

O app abre no navegador (geralmente em `http://localhost:8501`).

## Como usar

1. **Identifique-se** na barra lateral com seu nome (sem espaços).
2. **Exporte sua fatura do Nubank em CSV**:
   1. Abra o app Nubank → **Cartão de Crédito** → **Resumo de Faturas**.
   2. Selecione o mês (apenas faturas **fechadas** têm opção CSV).
   3. Toque no ícone de envio (canto superior direito) → **CSV**.
   4. O arquivo chega por e-mail no endereço cadastrado na Nubank.
3. **Faça upload** do CSV no app.
4. Informe **com quem você divide despesas** (nomes separados por vírgula).
5. **Confirme cada compra**: categoria e quem participa da divisão.
6. Confira o **resumo** e o **detalhamento por pessoa**.
7. **Exporte** o resultado em Excel, se desejar.

## Estrutura de dados

- `fatura_<usuario>.db` — banco SQLite por usuário, com a tabela `historico` (descrição normalizada → categoria e lista de pessoas para dividir). Criado automaticamente na primeira execução.
- O formato de valores segue o padrão brasileiro (`1.037,52`) e é convertido automaticamente.

## Tecnologias

- [Streamlit](https://streamlit.io/) — interface web
- [pandas](https://pandas.pydata.org/) — manipulação dos dados da fatura
- [openpyxl](https://openpyxl.readthedocs.io/) — geração da planilha Excel
- [SQLite](https://www.sqlite.org/) — persistência do histórico de classificações
