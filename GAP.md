# Agent Interface GAP

## 目的

AIエージェントの「界面」を、単なるチャットUIではなく、**人間・エージェント・他エージェント・ツール・データ・環境を接続する定義面**として調査する。

## 現状の共通要素

現在のエージェント設計では、少なくとも次の要素が分離されつつある。

- **Identity** — agentは何者か
- **Instruction** — 何をするか / 何をしないか
- **Persona** — どういう存在として振る舞うか
- **Skill** — 何ができるか
- **Tool** — 具体的に何を実行できるか
- **Memory** — 何を保持するか
- **Workflow** — どういう手順で動くか
- **Model** — 推論を担うモデル
- **Context** — 何を知った状態で判断するか
- **Permission / Policy** — 何を実行してよいか
- **Evaluation** — どう評価するか
- **Interface** — 外部からどう呼び出すか

AgentDefの2026年ドラフトも identity / instructions / memory / tools / workflows / skills / runtime configuration / orchestration / evaluation を共通構成要素として整理している。 citeturn0search6

## プロトコル上の界面

### MCP

**Agent ↔ Tool / Data** の界面。

ツールやリソースを標準化して、エージェントが外部機能・データに接続する層。

### A2A

**Agent ↔ Agent** の界面。

A2AではAgent Cardによって identity / capabilities / skills / interaction requirements などを発見可能にする。Agent Skillにはid、name、description、tags、examples、input/output modesなどが含まれる。 citeturn0search1turn0search2

### Human Interface

**Human ↔ Agent** の界面。

チャットだけではなく、自然言語、構造化入力、ファイル、画像、音声、UIイベントなどを含む。

## GAP 1 — Agentの「人格」と「能力」が混ざっている

Persona / Identity / Skill / Tool が一つのsystem promptに埋め込まれることが多い。

必要なのは、

```text
WHO   = Identity / Persona
KNOW  = Context / Memory
CAN   = Skill / Tool
DO    = Workflow / Action
MAY   = Policy / Permission
SHOW  = Interface / Output
```

という分離。

## GAP 2 — 「Skill」と「Tool」の境界

Microsoftの整理では、Agentはrequestをオーケストレーションし、Skillは必要時にロードされるworkflow/capability、Toolはagentが呼び出す具体的なfunctionとして分けられている。 citeturn0search3

したがって、bonsai/agentsでは **Skill = 意味のある仕事単位、Tool = 実行単位** として定義できる可能性がある。

```text
Agent
 ├─ Skill
 │   ├─ workflow
 │   └─ reasoning pattern
 └─ Tool
     └─ executable function
```

## GAP 3 — 「思考型」がAgent Interfaceに入っていない

今回定義した6つの思考型を、Personaではなく **Thinking Interface** として扱う。

| Thinking Type | 操作 |
|---|---|
| Plato / essence | 本質を抽出する |
| Kant / condition | 成立条件を問う |
| Wittgenstein / language | 用法・文脈を調べる |
| Foucault / genealogy | 成立過程・制度を追う |
| Azuma / connection | 接続・環境を捉える |
| Sun Tzu / strategy | 状況・配置・行動を考える |

これは「誰になるか」ではなく、**どう考えるかを切り替える界面**として扱う。

## GAP 4 — Agent Cardが能力中心

A2AのAgent Cardはagent discoveryのための identity / capabilities / skills / interfaces を記述するが、**思考様式・価値観・判断手順・根拠の扱い方**まで標準的には十分表現しない。 citeturn0search2turn0search13

候補として、bonsai Agent Definitionに以下を追加する。

```yaml
thinking:
  types:
    - essence
    - condition
    - language
    - genealogy
    - connection
    - strategy
```

## GAP 5 — Agent ↔ Human と Agent ↔ Agent の界面が分離している

A2AはAgent-to-Agent、MCPはAgent-to-Toolという役割分担が明確になっている。 citeturn0search1

しかし、Humanが複数Agentを観察・比較・介入・承認する **Human ↔ Agent Community** の界面は別途必要。

```text
             Human
               │
        Human Interface
               │
          Agent Layer
        ┌──────┼──────┐
       A1      A2      A3
        │       │       │
       MCP     A2A     MCP
        │       │       │
      Tools   Agents   Data
```

## GAP 6 — Agent Communityの統治

複数Agentが協働する場合、単なるtask delegationだけでは不足する可能性がある。

調査対象として以下を追加する。

- membership
- role
- deliberation
- dissent
- human escalation
- decision provenance
- audit / replay
- permission

2026年の研究でも、agent interoperability protocolだけでは voting、dissent preservation、完全なdeliberationなどのgovernance primitivesが不足するという分析がある。 citeturn0academia25

## 暫定モデル

bonsai/agentsでは、Agentを次のように定義する。

```text
AGENT
│
├── Identity      WHO
├── Persona       HOW-TO-BE
├── Thinking      HOW-TO-THINK
├── Knowledge     WHAT-IT-KNOWS
├── Memory        WHAT-IT-REMEMBERS
├── Skill         WHAT-IT-CAN-DO
├── Tool          WHAT-IT-CAN-EXECUTE
├── Workflow      HOW-IT-ACTS
├── Policy        WHAT-IT-MAY-DO
├── Interface     HOW-OTHERS-TALK-TO-IT
└── Evaluation    HOW-WE-KNOW-IT-WORKS
```

## 次に調べること

1. Agent CardにThinking / Policy / Evaluationを追加できるか
2. `AGENTS.md` / `SKILL.md` / `PERSONA.md` / `Agent Card` の責務を比較する
3. MCP / A2A / AG-UI / A2UIの界面を整理する
4. Human ↔ Agent ↔ Agent ↔ Tool の共通Interaction Schemaを作る
5. `thinking.yaml` の最小仕様を作る
6. bonsai/agentsの各Agentをこの定義にマッピングする

## 参考

- Google Cloud: AI agentのrole / persona / memory / tools / modelの整理。 citeturn0search0
- Microsoft: Agent / Skill / Toolの責務分離。 citeturn0search3
- A2A: Agent discovery / Agent Card / Agent Skill / Agent Interface。 citeturn0search1turn0search2
- AgentDef: framework-agnosticなAgent Definitionの試み。 citeturn0search6

---

**仮説:** Agentの本当の「界面」はUIではなく、**定義（Definition）と実行（Runtime）の境界**にある。さらに、その上に「思考型」を差し込むことで、同じAgent/Skillを異なる認識論・分析方法で実行できる。
