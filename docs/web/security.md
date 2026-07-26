# 安全模型

## 信任与非目标

首版面向 2–4 位彼此认识的受邀用户，但仍把越权、恶意文件名、路径穿越和提示注入当作真实威胁。Linux 用户隔离可显著降低误读和普通越权风险，但它不是虚拟机：内核漏洞、root Runner 实现漏洞和可利用的本机服务仍可能突破隔离。

## 身份与浏览器

- 不公开注册；管理员创建账号并生成一次性临时密码。
- 密码使用 Argon2id，至少 12 个字符。
- 首次登录必须改密；管理员重置后可再次强制。
- 登录按“标准化用户名 + 客户 IP”记录，15 分钟最多 5 次失败。
- Cookie 为 `Secure`、`HttpOnly`、`SameSite=Lax`；生产只走 HTTPS。
- 写接口校验会话级 CSRF Token。
- Caddy 屏蔽 `/internal/*`；FastAPI 只监听 loopback。
- HTML 产物预览带 `sandbox` CSP，响应统一 `nosniff`。

## Linux 用户隔离

普通用户映射为 `jh_<内部UUID前12位>`：

- `useradd --system`，密码锁定，shell 为 `/usr/sbin/nologin`。
- 不加入 sudo、docker 或任何共享高权限组。
- HOME 和 workspace 都为 `0700`，仓库彼此独立。
- Claude 任务以该 UID/GID 的 transient unit 运行，使用独立 HOME。
- `NoNewPrivileges`、`PrivateTmp`、`PrivateDevices`、只读系统、内核保护、2 GB 内存、单核、128 进程和整组终止。
- 可信的项目权限设置、Git config 和固定 Python 脚本在任务期间只读绑定；Git hooks 由进程级配置固定为 `/dev/null`。

systemd 不是内容级命令过滤器。Claude 可见工具由只读项目设置、工具清单和 CLI allowlist 共同限制：Read/Write/Edit、Glob/Grep、Task、WebSearch/WebFetch、固定 Python 脚本及受限 Git。链接检查通过固定的 `check_links.py` 执行，并拒绝 localhost、私网和链路本地目标。`sudo`、Docker、包安装、系统写入和 `--dangerously-skip-permissions` 不在允许范围。权限询问不会自动批准。

## Runner

Runner 是唯一 root 常驻进程，也是最高风险组件：

- socket 为 `root:jobhunt-web 0660`，其他用户不能调用。
- 请求先做 UUID、session ID、文件名和相对路径验证。
- `run` 使用代码内构造的参数数组，不拼 shell，不接受命令和环境变量。
- 用户名、HOME、workspace 只从 root-owned registry 查找。
- 文件只允许白名单根目录；拒绝 `..`、绝对路径、符号链接和覆盖。
- 上传批次目录由 root 持有并设为只读，原文件和提取文本均为 `0444`；Claude 可以读取，但不能通过普通文件写入修改原始资料。
- PDF/DOCX 解析在独立低权限子进程中进行，限制 20 秒 CPU、512 MB 地址空间、输出体积和文件描述符；Web 端 30 秒未完成就终止。
- registry 为 `0600`，服务 `UMask=0077`。

修改 Runner 时应优先增加固定动作，而不是增加“通用执行”接口。任何 `command`、`path`、`env` 或 `linux_username` 外部参数都会破坏设计。

## DeepSeek Key 与额度

真实 Key 只在 `/etc/jobhunt/web.env`，Runner 和用户进程都拿不到。每次任务由 Web 签发带用户 ID、任务 ID、过期时间和随机 nonce 的 HMAC 内部 Token。代理每次请求都确认对应任务仍为 `running`，停止、失败、完成或服务重启都会立即撤销该 Token。代理只转发固定 DeepSeek host 和 Claude Code 需要的 Anthropic 路径。

额度是软限制：新任务开始前检查，已经运行的任务允许完成，因此单次任务可能使 Token 数略超限。计费依据 provider-reported usage，不使用 Claude 的 `--max-budget-usd`。停用账号会立刻让新代理请求失败，已有短期 Token 也无法绕过数据库的启用状态检查。

## 已知剩余风险

- WebSearch/WebFetch 允许联网，提示注入可能诱导 Claude 读取或改写用户自己工作区中的内容。
- V1 未实现按目标域名的内网/公网 egress 防火墙；项目脚本在该 Linux UID 下仍可发起网络连接。生产机不应与敏感内网共享无防火墙网络。
- Linux UID 隔离不等于容器/虚拟机隔离；不应给互不信任的公众使用。
- 上传提取库可能存在解析器漏洞，应固定并及时升级依赖。
- root Runner 必须小而可审计；不要让 Web 用户控制任意命令。
- 用户文件和聊天属于敏感数据，远程备份必须加密并限制凭证权限。
