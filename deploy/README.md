# 部署说明

## 1. 修改服务文件

编辑 `dietagent.service`，将以下字段替换为实际值：

| 字段 | 默认值 | 说明 |
|------|--------|------|
| `User` / `Group` | `ubuntu` | Linux 运行用户 |
| `WorkingDirectory` | `/home/ubuntu/DietAgent` | 项目路径 |
| `EnvironmentFile` | `/home/ubuntu/DietAgent/.env` | .env 路径 |
| `ExecStart` uv 路径 | `/home/ubuntu/.local/bin/uv` | `which uv` 查看 |
| `--workers` | `2` | CPU 核心数 × 2 + 1，异步项目 1~2 即可 |

## 2. 安装服务

```bash
# 复制服务文件
sudo cp deploy/dietagent.service /etc/systemd/system/

# 重载 systemd 并启用
sudo systemctl daemon-reload
sudo systemctl enable dietagent
sudo systemctl start dietagent
```

## 3. 常用命令

```bash
sudo systemctl restart dietagent   # 重启
sudo systemctl stop dietagent      # 停止
sudo systemctl status dietagent    # 查看状态
sudo journalctl -u dietagent -f    # 实时日志
sudo journalctl -u dietagent -n 100  # 最近 100 行日志
```
