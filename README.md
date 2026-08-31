# 📚 knowledge-bases

<div align="center">

```
██╗  ██╗ ███╗   ██╗  ██████╗  ██╗    ██╗ ██╗      ███████╗ ██████╗   ██████╗  ███████╗
██║ ██╔╝ ████╗  ██║ ██╔═══██╗ ██║    ██║ ██║      ██╔════╝ ██╔══██╗ ██╔═══██╗ ██╔════╝
█████╔╝  ██╔██╗ ██║ ██║   ██║ ██║ █╗ ██║ ██║      █████╗   ██║  ██║ ██║   ██║ █████╗
██╔═██╗  ██║╚██╗██║ ██║   ██║ ██║███╗██║ ██║      ██╔══╝   ██║  ██║ ██║   ██║ ██╔══╝
██║  ██╗ ██║ ╚████║ ╚██████╔╝ ╚███╔███╔╝ ███████╗ ███████╗ ██████╔╝ ╚██████╔╝ ███████╗
╚═╝  ╚═╝ ╚═╝  ╚═══╝  ╚═════╝   ╚══╝╚══╝  ═══════╝═══════╝╚═══════╝  ╚═════╝  ╚══════╝
             ┌─────────────── Knowledge Base Hub ───────────────────┐
             │  650+ Papers · 22 Deep Reviews · 27K+ stars in deps  │
             └──────────────────────────────────────────────────────┘
```

**Curated AI / Robotics / Research Knowledge Bases**

*GitHub-flavored dark futuristic landing page for 4 specialized AI research repositories.*

---

[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-LIVE-00FFFF?style=for-the-badge&logo=githubpages&logoColor=white)](https://ace-trump-tech.github.io/knowledge-bases/)
[![Knowledge Bases](https://img.shields.io/badge/Knowledge%20Bases-4-FF00FF?style=for-the-badge&logo=bookstack&logoColor=white)]()
[![Papers](https://img.shields.io/badge/Papers-650%2B-39FF14?style=for-the-badge&logo=arxiv&logoColor=black)]()
[![Status](https://img.shields.io/badge/Status-Maintained-00FF7F?style=for-the-badge&logo=checkmarx&logoColor=white)]()

</div>

---

## Reproducible checkout

This repository is a maintained hub, not a second copy of every paper or tool. The collections under [`bases/`](./bases/) and [`projects/`](./projects/) are Git submodules pinned to explicit upstream commits. Each entry remains an independent GitHub repository; the directory in this hub is only a versioned navigation point. This keeps history, licenses, and ownership clear while allowing one reproducible checkout.

### Clone everything

```bash
git clone --recurse-submodules https://github.com/ace-trump-tech/knowledge-bases.git
cd knowledge-bases
./scripts/bootstrap.sh --check
```

For an existing clone:

```bash
git submodule update --init --recursive
./scripts/bootstrap.sh --check
```

A plain `git clone` intentionally does not download submodules; this is standard Git behavior. Use `--recurse-submodules` or the bootstrap script instead of relying on filesystem symlinks, which do not carry another repository's contents and are fragile across machines.

### Maintained collections

| Path | Repository | Scope |
| --- | --- | --- |
| [`bases/driver-kb`](./bases/driver-kb) | [driver-kb](https://github.com/ace-trump-tech/driver-kb) | Autonomous driving |
| [`bases/embodied-ai-kb`](./bases/embodied-ai-kb) | [embodied-ai-kb](https://github.com/ace-trump-tech/embodied-ai-kb) | Embodied AI and robotics |
| [`bases/uav-gwm-kb`](./bases/uav-gwm-kb) | [uav-gwm-kb](https://github.com/ace-trump-tech/uav-gwm-kb) | UAV Gaussian world models |
| [`bases/research-skills`](./bases/research-skills) | [research-skills](https://github.com/ace-trump-tech/research-skills) | Research tools and workflows |

The power-grid self-learning materials are currently maintained separately and are not part of this hub's published submodules yet. They are deliberately not represented as a broken local symlink; add them here only after a stable public repository is available.

## Contribution policy

Please read [`CONTRIBUTING.md`](./CONTRIBUTING.md) before opening an issue or PR. We welcome human-maintained contributions, especially corrections with primary sources, reproducible import scripts, and carefully reviewed submodule updates. AI-generated issue reports, comments, PR descriptions, and review replies are not accepted; authors must be able to reproduce and explain their changes.

The hub only records pointers and maintenance metadata. Content changes belong in the relevant submodule, following that project's license and contribution policy.

## Independent project links

These directories are intentionally independent projects. On GitHub, click a directory to open the corresponding repository; locally, initialize submodules only when you also want a working copy.

| Path | Independent repository | Purpose |
| --- | --- | --- |
| [`projects/python-sdk`](./projects/python-sdk) | [python-sdk](https://github.com/ace-trump-tech/python-sdk) | MCP Python SDK fork and contribution work |
| [`projects/Paper-Harness`](./projects/Paper-Harness) | [Paper-Harness](https://github.com/ace-trump-tech/Paper-Harness) | Auditable multi-agent research harness |
| [`projects/paper-harness-professional`](./projects/paper-harness-professional) | [paper-harness-professional](https://github.com/ace-trump-tech/paper-harness-professional) | Professional CV research workflow |
| [`projects/paper-harness-undergraduate`](./projects/paper-harness-undergraduate) | [paper-harness-undergraduate](https://github.com/ace-trump-tech/paper-harness-undergraduate) | Beginner thesis workflow |
| [`projects/MindPaw`](./projects/MindPaw) | [MindPaw](https://github.com/ace-trump-tech/MindPaw) | Embedded embodied-AI robot platform |

---

## ⚡ OVERVIEW

```yaml
─────────────────────────────────────────────────────────────────
  SYSTEM:       knowledge-bases (GitHub Pages)
  PROFILE:      ace-trump-tech
  STACK:        Markdown · HTML5 · CSS3 · GitHub Pages
  GENERATED:    2026-08-31
  COVERAGE:     Autonomous Driving · Embodied AI · UAV · Research
  TOTAL PAPERS: 650+
  TOTAL DEEP:   87+ deep reviews
  TOTAL DOCS:   20+ innovation / roadmap docs
─────────────────────────────────────────────────────────────────
```

---

## 📦 THE 4 KNOWLEDGE BASES

<table>
<tr>
<td width="50%" valign="top">

### 🚗 [driver-kb](https://github.com/ace-trump-tech/driver-kb)

> **End-to-End Autonomous Driving Knowledge Base V2**

```yaml
├── 📄 Papers:      311
├── 🔬 Deep:        50 deep reviews
├── 🗺  Subtopics:   8 (perception · world model · IL · RL · LLM · planning · data · sim)
├── 💡 Innovation:  5 top-level + 8 roadmaps
├── 🤖 Agents:     4 Claude skills (beginner/researcher/practitioner/reviewer)
└── 📅 Span:        2017-2026
```

**Topics**: UniAD · GAIA-1 · VAD · Think2Drive · GPT-Driver · DiffusionDrive

</td>
<td width="50%" valign="top">

### 🤖 [embodied-ai-kb](https://github.com/ace-trump-tech/embodied-ai-kb)

> **Embodied AI Knowledge Base**

```yaml
├── 📄 Papers:      122
├── 🔬 Deep:        22 deep reviews
├── 🗺  Subtopics:   10 (VLA · manipulation · dexterous · humanoid · quadruped · nav · WM · tactile · data · sim2real)
├── 💡 Innovation:  6 top-level (future_outlook · idea_summaries · humanoid_landscape · open_problems · top_papers_2025)
├── 🛤  Roadmaps:    10 subtopic roadmaps
└── 📅 Span:        2018-2026
```

**Topics**: RT-2 · OpenVLA · π0 · Diffusion Policy · DreamerV3 · GR00T N1 · HumanPlus

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🚁 [uav-gwm-kb](https://github.com/ace-trump-tech/uav-gwm-kb)

> **UAV Gaussian World Model for Active Perception**

```yaml
├── 📄 Papers:      110
├── 🔬 Deep:        15 deep reviews
├── 🗺  Subtopics:   6 (GWM · world models · active perception · localization · VLN · 3DGS)
├── 💡 Innovation:  5 (architecture · task decomposition · opportunities · landscape · proposal)
├── 🎯 Focus:       GWM · GaussianDream · GaussianDWM · PC-NBV · LM-Nav · 3DGS-VLN
└── 📅 Span:        2018-2026
```

**Topics**: Active reconstruction · active localization · language-guided navigation

</td>
<td width="50%" valign="top">

### 🔬 [research-skills](https://github.com/ace-trump-tech/research-skills)

> **Research Tools & Skills Knowledge Base**

```yaml
├── 🛠  Tools:      107
├── 🗂  Categories: 10 (literature search · Claude Code skills · academic DB · AI assistants · writing · Zotero · Obsidian · arXiv · figures · workflow)
├── 🔄 Comparisons: 5 cross-category
├── 🚀 Workflows:  4 recommended
├── 💡 Insights:    selection-guide + starter-stacks
└── 📅 Span:        2023-2026
```

**Topics**: Claude Code Skills · Paper-harness · Semantic Scholar · Connected Papers · Zotero · Obsidian · Pandoc · Dataviz

</td>
</tr>
</table>

---

## 🔥 STATS

<div align="center">

| **Metric** | **Count** |
|:----------:|:---------:|
| 📚 **Knowledge Bases** | **4** |
| 📄 **Total Papers** | **650+** |
| 🔬 **Deep Reviews** | **87+** |
| 💡 **Innovation Docs** | **20+** |
| 🗺️ **Subtopic Roadmaps** | **28** |
| 🤖 **Claude Code Skills** | **4** (in driver-kb) |
| ⭐ **GitHub Stars** | **2.4K+** (across profile) |
| 🍴 **Total Forks** | **3K+** (across profile) |

</div>

---

## 🛠️ STACK

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend:   HTML5 · CSS3 (custom · no framework)          │
│  Typography: JetBrains Mono · Fira Code · SF Mono            │
│  Hosting:    GitHub Pages (ace-trump-tech.github.io/...)   │
│  Source:     Markdown → Pandoc rendered                     │
│  Style:      Dark futuristic · neon accents · ASCII art   │
└─────────────────────────────────────────────────────────────┘
```

### Color Palette

```css
:root {
  --bg:        #0d1117;   /* GitHub dark canvas   */
  --bg-2:      #010409;   /* deep black            */
  --fg:        #c9d1d9;   /* primary text          */
  --cyan:      #00ffff;   /* neon cyan accent      */
  --magenta:   #ff00ff;   /* neon magenta accent   */
  --green:     #39ff14;   /* neon green accent     */
  --muted:     #6e7681;   /* secondary text        */
  --border:    #30363d;   /* card border           */
}
```

---

## 🌐 ACCESS

### GitHub Pages (live landing page)
```
https://ace-trump-tech.github.io/knowledge-bases/
```

### Direct Repository Links
```
https://github.com/ace-trump-tech/driver-kb         (311 papers)
https://github.com/ace-trump-tech/embodied-ai-kb    (122 papers)
https://github.com/ace-trump-tech/uav-gwm-kb        (110 papers)
https://github.com/ace-trump-tech/research-skills   (107 tools)
```

---

## 📜 LICENSE

All knowledge bases are released under **MIT License**. Individual papers retain their original copyrights.

---

## 🧑‍💻 MAINTAINER

```
ace-trump-tech
GitHub: https://github.com/ace-trump-tech
Built with: Claude Opus · 2026
```

---

<div align="center">

```
[ ◢◣ Built for the research community ◢◣ ]
[   Every byte curated with intention     ]
```

</div>
