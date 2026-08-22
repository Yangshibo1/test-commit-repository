# Agent Execution DAG 可视化设计方案

## 1. 背景

在 Agent 系统中，模型执行过程通常包含：

* 用户任务（Task）
* Agent 规划（Planning）
* 工具调用（Tool Call）
* 代码执行（Execution）
* 中间产物（Artifact）
* 最终结果（Result）

这些执行过程天然形成一个有向无环图（Directed Acyclic Graph, DAG）。

对于 Agent Execution Trace、数据血缘分析（Data Lineage）和 W3C PROV 建模系统，需要设计一个能够：

* 展示执行链路
* 支持节点交互
* 展示数据依赖关系
* 支持实时更新
* 支持大规模 DAG 浏览

的前端可视化系统。

---

# 2. 整体架构

```text
                 Agent Runtime

                      |
                      |
              Execution Events

                      |
                      v

              AgentVAST Collector

                      |
                      v

          Provenance Graph / DAG Model

                      |
                      v

                  FastAPI

                      |
                      |
              WebSocket / REST API

                      |
                      v

                  Frontend

                      |
          +-----------+-----------+
          |                       |
    Graph Layout            Graph Rendering
          |                       |
      ELK / Dagre          React Flow
```

---

# 3. 前端技术方案

## 3.1 React Flow

推荐使用：

* React Flow

作为 DAG 渲染框架。

原因：

* 基于 React
* 支持自定义节点
* 支持节点拖拽
* 支持缩放和平移
* 支持边交互
* 适合 Agent Workflow 展示

数据结构：

```json
{
  "nodes": [
    {
      "id": "task_1",
      "type": "task",
      "data": {
        "label": "Analyze Dataset"
      }
    }
  ],
  "edges": [
    {
      "source": "task_1",
      "target": "tool_1"
    }
  ]
}
```

---

# 4. DAG 自动布局

## 4.1 为什么需要自动布局

Agent执行图通常不是简单链式结构：

```text
User
 |
Planner
 |
+--------+
|        |
SQL    Python
|        |
+--------+
 |
Result
```

手动设置节点坐标不可维护。

---

## 4.2 Dagre

适合中小规模 DAG。

流程：

```text
DAG Data

   |
   v

Dagre Layout

   |
   v

Node Position

   |
   v

React Flow Render
```

优点：

* 简单
* 集成方便
* 层级布局效果较好

---

## 4.3 ELK Layout

适合复杂 Agent DAG。

优势：

* 支持复杂约束
* 支持大规模图
* 布局质量高

推荐用于：

* Agent执行历史
* 数据血缘图
* 多分支任务流

---

# 5. 节点设计

DAG节点不应该只是简单圆点。

应该根据语义设计不同节点类型。

## 5.1 Task Node

表示用户任务或Agent任务。

示例：

```text
+----------------+
| Task           |
+----------------+
| Analyze CSV    |
| Status: Done   |
| Time: 20s      |
+----------------+
```

属性：

```json
{
"type":"task",
"status":"completed",
"duration":20
}
```

---

## 5.2 Tool Node

表示工具调用。

例如：

* Python
* SQL
* MCP Tool
* API

示例：

```text
+----------------+
| Tool Call      |
+----------------+
| python_execute |
| pandas         |
| 2.5s           |
+----------------+
```

---

## 5.3 Artifact Node

表示数据产物。

例如：

* CSV
* JSON
* 图片
* 模型文件

示例：

```text
+----------------+
| Artifact       |
+----------------+
| result.csv     |
| hash: abc123   |
+----------------+
```

---

# 6. 边设计

普通 DAG：

```text
A ----> B
```

Provenance DAG：

边应该具有语义。

例如：

```text
Python Execution

       |
       | generated
       v

result.csv
```

边属性：

```json
{
"source":"python_node",
"target":"artifact_node",
"type":"generated",
"time":"12:01:03"
}
```

支持：

* generated
* used
* derived_from
* triggered_by

---

# 7. 交互设计

## 7.1 节点点击

点击节点展示：

* 输入
* 输出
* 参数
* 执行时间
* 日志
* Artifact信息

例如：

```text
Node Detail

Name:
python_analysis

Input:
data.csv

Output:
result.csv

Duration:
3.2s

Status:
Success
```

---

## 7.2 DAG过滤

支持：

按照类型过滤：

* Task
* Tool
* Artifact

按照状态过滤：

* Success
* Failed
* Running

---

## 7.3 执行过程动画

实时Agent执行：

```text
Planner
   |
   v
Python Tool
   |
   v
Artifact
```

节点状态：

```
Waiting
   |
Running
   |
Success
```

---

# 8. 数据模型设计

推荐使用：

## W3C PROV + DAG

映射：

| PROV概念   | DAG节点          |
| -------- | -------------- |
| Entity   | Artifact       |
| Activity | Tool Execution |
| Agent    | LLM Agent      |

示例：

```text
Agent

 |
wasAssociatedWith

 |

Activity

 |
used

 |

Entity
```

转换：

```text
PROV Graph

      |

DAG Converter

      |

React Flow JSON
```

---

# 9. 后端接口设计

## 获取DAG

```http
GET /api/trace/{id}
```

返回：

```json
{
"nodes":[],
"edges":[]
}
```

---

## 实时更新

使用：

```text
WebSocket
```

事件：

```json
{
"type":"node_update",
"node":"python_1",
"status":"running"
}
```

---

# 10. 推荐技术栈

## Frontend

```text
React
 |
React Flow
 |
ELK / Dagre
 |
SVG Rendering
```

## Backend

```text
FastAPI

+

AgentVAST

+

W3C PROV

+

Graph Database
```

---

# 11. 针对 Agent Execution Trace 的推荐方案

最终架构：

```text
                LLM Agent

                    |

             Tool Execution

                    |

             Trace Collector

                    |

             Provenance DAG

                    |

                 FastAPI

                    |

               WebSocket

                    |

                  React

                    |

          React Flow + ELK

                    |

              Interactive DAG
```

该方案能够支持：

* Agent执行过程追踪
* 数据血缘分析
* 中间产物管理
* 执行回放
* 多Agent协作分析

---

# 12. 总结

对于 Agent Execution DAG 可视化：

推荐：

* 使用 React Flow 作为图交互框架
* 使用 ELK/Dagre 进行自动布局
* 使用 SVG 实现节点级交互
* 使用 PROV 模型提供语义
* 使用 WebSocket 支持实时执行展示

重点不应该放在重新实现 DAG 绘制，而应该关注：

> 如何将 Agent 执行过程转换为具有语义的可解释 Provenance Graph。

```
```
