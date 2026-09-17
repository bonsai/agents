# Agent Interface GAP

## 目的

AIエージェントの「界面」を、単なるチャットUIではなく、**人間・エージェント・他エージェント・ツール・データ・環境を接続する定義面**として調査する。

## GAP 1 — Agentの人格と能力の分離

```text
WHO   = Identity / Persona
KNOW  = Context / Memory
CAN   = Skill / Tool
DO    = Workflow / Action
MAY   = Policy / Permission
SHOW  = Interface / Output
```

## GAP 2 — SkillとToolの境界

**Skill = 意味のある仕事単位、Tool = 実行単位** として定義する可能性がある。

```text
Agent
 ├─ Skill
 │   ├─ workflow
 │   └─ reasoning pattern
 └─ Tool
     └─ executable function
```

## GAP 3 — Thinking Interface

Thinking TypeをPersonaではなく、**どう考えるかを切り替える界面**として扱う。

| Thinking Type | 基本操作 |
|---|---|
| Plato / essence | 本質を抽出する |
| Kant / condition | 成立条件を問う |
| Wittgenstein / language | 用法・文脈を調べる |
| Foucault / genealogy | 成立過程・制度を追う |
| Azuma / connection | 接続・環境を捉える |
| Sun Tzu / strategy | 状況・配置・行動を考える |

## GAP 4 — Agent Cardが能力中心

Agent discoveryの定義には、identity / capabilities / skills / interfacesだけでなく、**思考様式・判断手順・根拠の扱い方**を表現する余地がある。

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

## GAP 5 — Human ↔ Agent ↔ Agent ↔ Tool

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

Humanが複数Agentを観察・比較・介入・承認する **Human ↔ Agent Community** の界面が必要。

## GAP 6 — Agent Communityの統治

複数Agentが協働する場合、membership / role / deliberation / dissent / human escalation / decision provenance / audit / replay / permission が必要になる。

## GAP 7 — Environment Interface

落合陽一の「計算機自然」は、人・機械・物質世界・仮想世界の間に多様な選択肢を生む世界像として位置づけられている。研究室も人・計算機・自然の間で新たな文化的価値を実装することを掲げている。これはAgentを孤立した人格としてではなく、**人間・計算機・物理環境・データ環境の境界で動く存在**として考える材料になる。 citeturn0search2turn0search4

```text
Agent
 ├─ Thinking
 ├─ Knowledge
 ├─ Tools
 └─ Environment
       ├─ human
       ├─ physical world
       ├─ digital world
       └─ other agents
```

したがって **Environment Interface** を独立した定義として検討する。

## GAP 8 — Implementation Interface

安野貴博の公式発信では、テクノロジーを「できなかったことを、できるようにする方法」と捉え、政治・行政の透明化・効率化や参加のための技術利用を掲げている。ここからAgent設計上、**問い・問題を仕様、実装、運用、改善へ変換する界面**を抽出できる。これは特定の政策評価ではなく、実装プロセスの設計パターンとして扱う。 citeturn0search1

```text
Question
   ↓
Problem
   ↓
Specification
   ↓
Implementation
   ↓
Operation
   ↓
Feedback
   ↺
```

この型を **Implementation Interface** と仮称する。

## 思考型の拡張仮説

| Thinking / Operating Type | 基本操作 |
|---|---|
| Plato / essence | 本質を抽出する |
| Kant / condition | 成立条件を問う |
| Wittgenstein / language | 用法・文脈を調べる |
| Foucault / genealogy | 成立過程・制度を追う |
| Azuma / connection | 接続・環境を捉える |
| Sun Tzu / strategy | 状況・配置・行動を考える |
| Ochiai / environment | 人・機械・物質・データの境界を再構成する |
| Anno / implementation | 問題を仕様・実装・運用へ変換する |

※「Ochiai」「Anno」は本人の思想を完全に表現する分類名ではなく、公開されている活動・概念からAgent設計のために抽出した**作業仮説**である。

## 暫定モデル

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
├── Environment   WHERE-IT-ACTS
├── Policy        WHAT-IT-MAY-DO
├── Interface     HOW-OTHERS-TALK-TO-IT
└── Evaluation    HOW-WE-KNOW-IT-WORKS
```

## 次に調べること

1. Agent CardにThinking / Environment / Policy / Evaluationを追加できるか
2. `AGENTS.md` / `SKILL.md` / `PERSONA.md` / `Agent Card` の責務を比較する
3. MCP / A2A / AG-UI / A2UIの界面を整理する
4. Human ↔ Agent ↔ Agent ↔ Tool ↔ Environment の共通Interaction Schemaを作る
5. `thinking.yaml` の最小仕様を作る
6. `environment.yaml` の最小仕様を作る
7. bonsai/agentsの各Agentをこの定義にマッピングする
8. 「思考型」と「実行型」を分離する

## 参考

- 落合陽一公式: Digital Nature / Artist Statement。 citeturn0search2turn0search4
- 安野貴博 / チームみらい公式: テクノロジーを用いた問題解決・参加の考え方。 citeturn0search1

---

**仮説:** Agentの本当の「界面」はUIではなく、**定義（Definition）と実行（Runtime）の境界**にある。その上に「思考型」、横に「環境」、下流に「実装変換」を差し込むことで、Agentを単なるPersonaやTool wrapperではなく、**問いを受け、世界を認識し、考え、実装し、環境へ作用する存在**として定義できる。
