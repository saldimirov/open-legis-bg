# open-legis Architecture

## System Overview

```mermaid
graph TB
    subgraph Source["Data Source"]
        DV["dv.parliament.bg\n(State Gazette)"]
    end

    subgraph Scraper["Scraper Layer"]
        IDX["dv_index.py\ncrawl_year()\n→ .dv-index.json"]
        CLI_SCRAPE["CLI: scrape-dv-batch\n--from-year / --to-year\n--types zakon,zid,...\n--resume"]
        DV_CLIENT["dv_client.py\nget_issue_materials(idObj)\nget_material_text(idMat)"]
        DV_TO_AKN["dv_to_akn.py\nHTML → AKN XML\ndetect_act_type()\nconvert_material()"]
    end

    subgraph Fixtures["Fixtures (git)"]
        AKN_FILES["fixtures/akn/\n{act_type}/{year}/{slug}/\n  expressions/{date}.bul.xml"]
        RELATIONS["fixtures/akn/relations/\namendments.yaml"]
    end

    subgraph Load["Loader Layer"]
        CLI_LOAD["CLI: open-legis load\n--if-empty"]
        AKN_PARSER["akn_parser.py\nAKN XML → Work + Expression\n+ Element rows"]
        AMEND_MATCH["amendment_matcher.py\nJaccard similarity\nZID → base law"]
        RELATIONS_LOADER["relations.py\namendments.yaml → Amendment rows"]
    end

    subgraph DB["PostgreSQL"]
        WORK["work\neli_uri, act_type, title\ndv_broy, dv_year, dv_position"]
        EXPR["expression\nwork_id, date, language\nis_latest"]
        ELEM["element\nexpression_id, e_id\ntype, num, text, tsvector"]
        AMEND["amendment\namending_work_id → target_work_id\noperation, effective_date"]
        REF["reference\nsource_expression_id, source_e_id\ntarget_work_id (nullable)\nraw_text, resolved"]
        EXT_ID["external_id\nwork_id, source, external_value"]
    end

    subgraph API["FastAPI Application"]
        direction TB
        APP["app.py\nSlowAPI rate limiting\nETag middleware\nSecurity headers\nCORS"]
        
        subgraph Routes["Routes"]
            UI["/ui/...\nJinja2 server-rendered UI"]
            ELI["/eli/bg/{type}/{year}/{slug}\nELI standard\nJSON + AKN XML + Turtle"]
            DISC["/v1/works\n/v1/search\n/v1/works/{slug}/amendments\n/v1/works/{slug}/references\n/v1/works/{slug}/expressions"]
            ALIAS["/v1/by-dv/{year}/{broy}/{pos}\n/v1/by-external/{source}/{id}"]
            DUMPS["/v1/dumps/"]
            META["/health\n/robots.txt"]
        end

        MCP["/mcp\nMCP server for AI agents"]
    end

    subgraph Search["Search"]
        FTS["search/query.py\nPostgreSQL tsvector\nBulgarian simple dictionary\nts_rank + ts_headline"]
    end

    subgraph Dumps["Dumps"]
        DUMP_BUILD["dumps/build.py\nbuild_tarball()\nbuild_sql_dump()"]
        DUMP_FILES["dumps/\nlatest.tar.gz\nlatest.sql.gz"]
    end

    %% Scraper flow
    DV -->|"broeveList.faces (POST)\n→ idObj list"| IDX
    IDX --> CLI_SCRAPE
    CLI_SCRAPE --> DV_CLIENT
    DV_CLIENT -->|"materiali.faces?idObj=X\n→ idMat list"| DV
    DV_CLIENT -->|"showMaterialDV.jsp?idMat=X\n→ HTML"| DV
    DV_TO_AKN --> AKN_FILES
    CLI_SCRAPE --> DV_TO_AKN

    %% Load flow
    AKN_FILES --> CLI_LOAD
    CLI_LOAD --> AKN_PARSER
    CLI_LOAD --> RELATIONS_LOADER
    AKN_PARSER --> WORK
    AKN_PARSER --> EXPR
    AKN_PARSER --> ELEM
    RELATIONS_LOADER --> RELATIONS
    RELATIONS_LOADER --> AMEND
    AMEND_MATCH -->|"CLI: match-amendments"| AMEND

    %% DB relations
    WORK --> EXPR
    EXPR --> ELEM
    WORK --> AMEND
    WORK --> REF
    WORK --> EXT_ID

    %% API
    APP --> Routes
    APP --> MCP
    ELEM --> FTS
    FTS --> DISC
    DB --> ELI
    DB --> DISC
    DB --> ALIAS
    
    %% Dumps
    DB --> DUMP_BUILD
    AKN_FILES --> DUMP_BUILD
    DUMP_BUILD --> DUMP_FILES
    DUMP_FILES --> DUMPS
```

## Data Flow: Scraping

```mermaid
sequenceDiagram
    participant CLI as scrape-dv-batch
    participant IDX as dv_index.py
    participant DV as dv.parliament.bg
    participant AKN as dv_to_akn.py
    participant FS as fixtures/akn/

    CLI->>IDX: load .dv-index.json (cached)
    IDX-->>CLI: list of DvIssue(idObj, broy, year, date)

    loop for each issue
        CLI->>DV: GET materiali.faces?idObj=X
        DV-->>CLI: HTML with idMat list

        loop for each material
            CLI->>DV: GET showMaterialDV.jsp?idMat=X
            DV-->>CLI: HTML (title + body text)
            CLI->>AKN: detect_act_type(title)
            AKN-->>CLI: act_type (zakon/zid/byudjet/...)
            CLI->>AKN: convert_material(title, body, issue)
            AKN-->>CLI: (slug, AKN XML string)
            CLI->>FS: write {act_type}/{year}/{slug}/expressions/{date}.bul.xml
        end
    end
```

## Data Flow: Loading into DB

```mermaid
sequenceDiagram
    participant CLI as open-legis load
    participant PARSER as akn_parser.py
    participant AMEND as amendment_matcher.py
    participant DB as PostgreSQL

    CLI->>DB: check work count (--if-empty)
    CLI->>PARSER: parse each .bul.xml

    loop for each XML file
        PARSER->>DB: upsert Work (eli_uri, act_type, dv_broy, ...)
        PARSER->>DB: upsert Expression (work_id, date, language, is_latest)
        PARSER->>DB: upsert Element rows (e_id, type, num, text, tsvector)
    end

    CLI->>AMEND: load amendments.yaml → Amendment rows
    Note over AMEND,DB: CLI: match-amendments (separate step)<br/>Jaccard similarity on titles<br/>ZID → base zakon/kodeks
```

## AKN XML Structure (Akoma Ntoso 3.0)

```
fixtures/akn/zakon/2024/za-foo/
└── expressions/
    └── 2024-12-15.bul.xml
        └── <akomaNtoso>
              <act name="zakon">
                <meta>
                  <identification>
                    <FRBRwork> <FRBRuri>/eli/bg/zakon/2024/za-foo</FRBRuri>
                  <body>
                    <chapter eId="chp_1">
                      <section eId="sec_1">
                        <article eId="art_1">
                          <paragraph eId="art_1__para_1">
                          <point eId="art_1__para_1__pt_1">
                    <hcontainer name="final-provisions" eId="sec_final">
                      <hcontainer name="paragraph" eId="sec_final__para_1">  ← § items
```

## Database Schema

```mermaid
erDiagram
    work {
        uuid id PK
        string eli_uri UK
        string act_type
        string title
        int dv_broy
        int dv_year
        int dv_position
        string status
    }
    expression {
        uuid id PK
        uuid work_id FK
        date expression_date
        string language
        bool is_latest
    }
    element {
        uuid id PK
        uuid expression_id FK
        string e_id
        string type
        string num
        text text
        tsvector fts
        ltree path
    }
    amendment {
        uuid id PK
        uuid amending_work_id FK
        uuid target_work_id FK
        string target_e_id
        string operation
        date effective_date
        text notes
    }
    reference {
        uuid id PK
        uuid source_expression_id FK
        string source_e_id
        uuid target_work_id FK
        string target_e_id
        string reference_type
        text raw_text
        bool resolved
    }
    external_id {
        uuid id PK
        uuid work_id FK
        string source
        string external_value
    }

    work ||--o{ expression : "has versions"
    expression ||--o{ element : "contains"
    work ||--o{ amendment : "amended by (target)"
    work ||--o{ amendment : "amends (amending)"
    expression ||--o{ reference : "cites"
    work ||--o{ external_id : "known as"
```

## API Route Map

| Method | Path | Auth | Rate limit | Description |
|--------|------|------|-----------|-------------|
| GET | `/ui/` | — | — | Homepage (server-rendered) |
| GET | `/ui/works/{uri}` | — | — | Work detail page |
| GET | `/eli/bg/{type}/{year}/{slug}` | — | 300/min | Work (JSON / AKN XML / Turtle) |
| GET | `/eli/bg/{type}/{year}/{slug}/{date}/{lang}` | — | 300/min | Expression |
| GET | `/eli/bg/{type}/{year}/{slug}/{date}/{lang}/{eId}` | — | 300/min | Element |
| GET | `/v1/works` | — | 120/min | List all works (paginated) |
| GET | `/v1/search` | — | 60/min | Full-text search |
| GET | `/v1/works/{slug}/amendments` | — | — | Amendment graph |
| GET | `/v1/works/{slug}/references` | — | — | Citation graph |
| GET | `/v1/works/{slug}/expressions` | — | — | Version history |
| GET | `/v1/by-dv/{year}/{broy}/{pos}` | — | — | DV reference → 301 ELI redirect |
| GET | `/v1/by-external/{source}/{id}` | — | — | External ID → 301 ELI redirect |
| GET | `/v1/dumps/` | — | — | List available dumps |
| GET | `/v1/dumps/{name}` | — | 10/day | Download dump file |
| GET | `/health` | — | — | Health check |
| GET | `/robots.txt` | — | — | Robots policy |
| * | `/mcp` | — | — | MCP server (AI agents) |

## ELI URI Scheme

```
/eli/bg/{act_type}/{year}/{slug}                         ← Work
/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}           ← Expression
/eli/bg/{act_type}/{year}/{slug}/{date}/{lang}/{eId}     ← Element

Example:
/eli/bg/zakon/2024/za-darzhavnia-byudzhet
/eli/bg/zakon/2024/za-darzhavnia-byudzhet/2024-12-15/bul
/eli/bg/zakon/2024/za-darzhavnia-byudzhet/2024-12-15/bul/art_42
```
