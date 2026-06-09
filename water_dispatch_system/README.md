# 跨流域调水工程调度监控系统

南水北调工程全线调度监控平台，覆盖3条输水干渠、20个泵站、50个闸门、100个水位计和流量计的实时监控与智能调度。

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        调度中心大屏 / 手机APP                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────┐   │
│  │ KPI卡片  │  │ 告警列表 │  │ 调度面板 │  │ WebSocket推送 │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬────────┘   │
└───────┼──────────────┼──────────────┼───────────────┼───────────┘
        │              │              │               │
┌───────┴──────────────┴──────────────┴───────────────┴───────────┐
│                     Frontend (Canvas + Leaflet)                  │
│  ┌─────────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ plain_map.js    │  │profile_view.js│  │    app.js        │   │
│  │ Leaflet平面图   │  │ Canvas纵剖面  │  │  协调器/API/WS   │   │
│  └─────────────────┘  └──────────────┘  └──────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP / WebSocket
┌────────────────────────────┴────────────────────────────────────┐
│                 FastAPI Backend (gunicorn + uvicorn workers)     │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌────────┐│
│  │ dtu_receiver │ │water_balance │ │command_      │ │alarm_  ││
│  │ 水情采集校验 │ │_solver      │ │dispatcher    │ │monitor ││
│  │              │ │水量平衡求解 │ │MQTT指令下发  │ │告警推送││
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └───┬────┘│
│         │                │                │              │     │
│  ┌──────┴────────────────┴────────────────┴──────────────┴───┐ │
│  │              Redis Pub/Sub (模块间异步通信)                 │ │
│  │  channel:sensor_data / dispatch_command / alarm_event     │ │
│  └───────────────────────────────────────────────────────────┘ │
└──────────┬────────────────┬────────────────┬───────────────────┘
           │                │                │
    ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐
    │ PostgreSQL  │  │    Redis    │  │Mosquitto MQTT│
    │ + PostGIS   │  │  Pub/Sub   │  │ QoS1+持久会话│
    │ 空间索引    │  │  AOF持久化  │  │ 离线消息队列│
    │ 自动真空    │  │  LRU淘汰   │  │             │
    └─────────────┘  └─────────────┘  └──────┬──────┘
                                              │
                              ┌───────────────┴───────────────┐
                              │                               │
                       ┌──────┴──────┐                 ┌──────┴──────┐
                       │DTU模拟器    │                 │PLC模拟器    │
                       │100传感器    │                 │闸门开度反馈 │
                       │水位突变注入 │                 │泵站启停反馈 │
                       │通信中断模拟 │                 │状态持久跟踪 │
                       └─────────────┘                 └─────────────┘
```

## 快速部署

### 环境要求

- Docker 20.10+
- Docker Compose 2.0+
- 4GB+ 内存

### 一键启动

```bash
cd water_dispatch_system
docker-compose up -d
```

启动后访问 http://localhost:8000

### 逐服务启动

```bash
# 仅启动基础设施
docker-compose up -d postgres redis mosquitto

# 等待数据库就绪后启动后端
docker-compose up -d backend

# 启动模拟器
docker-compose up -d dtu-simulator plc-simulator
```

### 查看日志

```bash
# 后端日志
docker-compose logs -f backend

# DTU模拟器日志
docker-compose logs -f dtu-simulator

# PLC模拟器日志
docker-compose logs -f plc-simulator

# 全部日志
docker-compose logs -f
```

### 停止与清理

```bash
# 停止所有服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v
```

## DTU模拟器用法

### 场景模式

| 场景 | 说明 | 异常率 | 突变幅度 | 断线概率 |
|------|------|--------|----------|----------|
| `normal` | 正常运行 | 5% | 无 | 0% |
| `surge` | 水位突变 | 5% | ±30% | 0% |
| `outage` | 通信中断 | 5% | 无 | 15%/30s |
| `surge_and_outage` | 突变+中断 | 10% | ±35% | 20%/60s |
| `extreme` | 极端工况 | 30% | ±50% | 30%/120s |

### 命令行参数

```bash
python dtu_simulator.py \
  --api-url http://localhost:8000 \   # 后端地址
  --interval 300 \                    # 上报间隔(秒)
  --api-key dtu-secret-key-2024 \     # API密钥
  --scenario surge                    # 初始场景
```

### Docker环境变量

```yaml
environment:
  API_URL: http://backend:8000
  DTU_API_KEY: dtu-secret-key-2024
  DTU_INTERVAL: "300"
  DTU_SCENARIO: surge   # normal|surge|outage|surge_and_outage|extreme
```

### 运行时交互

DTU模拟器启动后支持stdin命令动态切换场景：

```bash
# 进入DTU容器交互
docker attach water_dispatch_dtu

# 切换到水位突变场景
surge

# 切换到极端工况
extreme

# 手动注入60秒通信中断
outage 60

# 恢复正常运行
normal

# 查看当前状态
status

# 查看帮助
help
```

## PLC模拟器用法

PLC模拟器订阅 `dispatch/command/#` 话题（QoS 1），接收闸门开度和泵站启停指令后反馈执行结果。

### 命令行参数

```bash
python plc_simulator.py \
  --broker localhost \    # MQTT Broker地址
  --port 1883             # MQTT端口
```

### 状态跟踪

PLC模拟器内部维护所有闸门和泵站的当前状态：

- **闸门**: `gate_states[gate_id] = {opening, flow, status}`
- **泵站**: `pump_states[station_id] = {running_count, total_power, total_flow, status}`

### 响应格式

闸门指令响应：
```json
{
  "command_id": "123",
  "target_type": "gate",
  "target_id": 1,
  "status": "executed",
  "timestamp": "2026-06-09T10:30:00Z",
  "actual_value": 75.2,
  "gate_opening": 75.2,
  "gate_flow": 75.2
}
```

泵站指令响应：
```json
{
  "command_id": "124",
  "target_type": "pump",
  "target_id": 1,
  "status": "executed",
  "timestamp": "2026-06-09T10:30:01Z",
  "actual_value": 2,
  "running_count": 3,
  "total_power": 1501.5,
  "total_flow": 74.8
}
```

### 持久会话

PLC模拟器使用 `clean_session=False` + `client_id="plc-simulator-001"`，MQTT Broker会保留离线期间的消息，重连后自动补发。

## API端点

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| DTU | POST | `/api/dtu/data` | DTU数据上报 |
| DTU | GET | `/api/dtu/sensors` | 传感器列表+实时值 |
| DTU | GET | `/api/dtu/sensors/{id}/history` | 传感器24h趋势 |
| 水量平衡 | POST | `/api/water-balance/plan` | 生成调度方案 |
| 水量平衡 | GET | `/api/water-balance/balance/{canal_id}` | 渠段水量平衡 |
| 水量平衡 | GET | `/api/water-balance/kpi/water-balance` | 全线水量总平衡 |
| 水量平衡 | GET | `/api/water-balance/kpi/water-levels` | 各渠段水位+偏差 |
| 水量平衡 | GET | `/api/water-balance/canals` | 干渠列表(GeoJSON) |
| 调度 | GET | `/api/dispatch/commands` | 调度指令列表 |
| 调度 | POST | `/api/dispatch/commands/{id}/cancel` | 取消指令 |
| 调度 | GET | `/api/dispatch/gates` | 闸门列表+状态 |
| 调度 | GET | `/api/dispatch/pump-stations` | 泵站列表+状态 |
| 调度 | GET | `/api/dispatch/kpi/pump-power` | 泵站总功率 |
| 告警 | GET | `/api/alarm/` | 告警列表 |
| 告警 | POST | `/api/alarm/acknowledge` | 确认告警 |
| 告警 | GET | `/api/alarm/stats` | 告警统计 |
| 系统 | GET | `/ws` | WebSocket实时推送 |
| 系统 | GET | `/docs` | Swagger文档 |

## 配置

所有参数通过 [config.yaml](backend/app/config.yaml) 加载，支持环境变量覆盖：

| 配置块 | 关键参数 | 环境变量前缀 |
|--------|----------|-------------|
| water_balance | gravity, wave_speed_factor, loss_rate... | `WB_` |
| alarm | level1_duration_minutes, level2_deviation... | `ALARM_` |
| dispatch | ramp_time_minutes, pump_stop_threshold... | — |
| mqtt | broker, port, queue_max_size... | `MQTT_` |
| redis | url, channels | `REDIS_` |
| dtu | api_key, report_interval | `DTU_` |

## 项目结构

```
water_dispatch_system/
├── backend/
│   ├── Dockerfile              # 多阶段构建 (builder → runtime)
│   ├── gunicorn_conf.py        # gunicorn配置 (uvicorn worker)
│   ├── requirements.txt
│   └── app/
│       ├── config.yaml         # YAML参数配置
│       ├── config.py           # 配置加载 (YAML + 环境变量)
│       ├── database.py         # SQLAlchemy异步引擎
│       ├── models.py           # ORM模型
│       ├── schemas.py          # Pydantic模型
│       ├── main.py             # FastAPI入口 + Gzip + WebSocket
│       ├── routers/
│       │   ├── dtu_receiver.py       # 水情采集路由
│       │   ├── water_balance_solver.py # 水量平衡路由
│       │   ├── command_dispatcher.py   # 指令调度路由
│       │   └── alarm_monitor.py       # 告警监控路由
│       └── services/
│           ├── redis_service.py        # Redis Pub/Sub
│           ├── dtu_receiver.py         # 水情采集服务
│           ├── water_balance_solver.py # 水量平衡求解
│           ├── command_dispatcher.py   # MQTT指令调度
│           └── alarm_monitor.py        # 告警评估推送
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── plain_map.js        # Leaflet地图组件
│       ├── profile_view.js     # Canvas纵剖面组件
│       └── app.js              # 协调器
├── database/
│   ├── init.sql                # 数据库初始化
│   └── postgis_tuning.sql      # PostGIS调优+索引+自动真空
├── simulator/
│   ├── dtu_simulator.py        # DTU模拟器 (5场景+交互)
│   ├── plc_simulator.py        # PLC模拟器 (状态跟踪+QoS1)
│   ├── Dockerfile.dtu
│   └── Dockerfile.plc
├── docker-compose.yml
├── mosquitto.conf               # MQTT Broker (持久化+QoS1)
└── README.md
```
