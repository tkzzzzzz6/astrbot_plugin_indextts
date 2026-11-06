# AstrBot IndexTTS 插件

> 基于本地 [IndexTTS](https://github.com/index-tts/index-tts) 的文本转语音插件，支持**音色克隆**与 **LLM 回复自动转语音**。

本仓库是 [原插件](https://github.com/zhou-error/astrbot_plugin_indextts) 的兼容性修复 fork。
2.0.2 根据 Gradio `/gen_single` 的接口定义适配参数，支持旧版接口及带
`lang_choice` / `duration_factor` 的新版接口（IndexTTS 2.5 WebUI）。

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/平台-AstrBot-orange?style=flat-square" alt="AstrBot">
  <img src="https://img.shields.io/badge/引擎-IndexTTS-green?style=flat-square" alt="IndexTTS">
  <img src="https://img.shields.io/badge/许可-MIT-lightgrey?style=flat-square" alt="License">
</p>

---

## 功能

- `/tts <文本>`：使用个人音色或默认音色生成语音（单次最多 1000 字）。
- `/tts_voice <URL>`：用公网音频 URL 设置个人音色；也可以直接发送一条语音消息并附带 `/tts_voice`。
- `/tts_reset_voice`：删除个人音色，恢复默认参考音频。
- `/tts_auto on|off`：**按会话**开启/关闭自动 TTS，不影响其他用户。
- `/tts_params`：查看本会话自动 TTS 状态、音色状态和推理参数。
- 自动 TTS：默认开启；只有在存在参考音频（个人音色或默认音色）时才会对 LLM 回复生成语音。

> 自动 TTS 只处理 **LLM 结果**，不会把 `/tts_params` 等命令回复读出来。
> 插件会检测 AstrBot 内置 TTS provider 是否已启用并主动跳过；如果你的
> AstrBot 版本不支持该检测，建议仍然只启用其中一个 TTS。
> 长文本转图片（t2i）与自动 TTS 同时生效时，框架可能在钩子之后把消息替换为
> 图片并丢弃语音，建议按需二选一。

## 插件结构

```text
astrbot_plugin_indextts/
├── _conf_schema.json      # WebUI 配置 schema
├── main.py                # Star 类、指令与事件钩子
├── core/
│   ├── audio.py           # 下载、校验、原子写入、清理
│   ├── api.py             # 根据 Gradio 接口定义映射新旧参数
│   ├── client.py          # 异步 IndexTTS 客户端
│   ├── config.py          # 默认值、类型转换、旧配置迁移
│   ├── paths.py           # 数据目录、用户音色路径
│   └── text.py            # 指令参数与 TTS 文本清理
├── metadata.yaml
├── requirements.txt
├── tests/
└── README.md
```

## 安装

需要 **AstrBot >= 4.16**、**Python 3.10+**，以及可访问的 IndexTTS Gradio WebUI。

```bash
cp -r astrbot_plugin_indextts /path/to/AstrBot/data/plugins/
# 然后在 AstrBot WebUI 的插件管理页重载插件
```

依赖：`gradio_client >= 1.0, < 3`、`httpx >= 0.24`。

也可以在 AstrBot WebUI 的插件管理中通过仓库地址安装本 fork：

```text
https://github.com/tkzzzzzz6/astrbot_plugin_indextts
```

已安装原插件时，请先备份插件配置及 `data/plugin_data/astrbot_plugin_indextts/`，
将插件更新来源切换到本 fork，再更新并重载。不要同时加载两份同名插件。
`metadata.yaml` 中的仓库地址已指向本 fork；已有安装的 Git `origin` 可能仍指向原仓库，
可在插件目录用 `git remote -v` 检查。改动必须先提交并推送到实际安装的分支，才能被远端更新获取。

## 配置

配置通过 **AstrBot WebUI → 插件 → IndexTTS 语音合成** 修改。插件使用 AstrBot 的配置系统，不再把插件目录下的 `data/config.json` 作为运行配置（仅首次启动时读取并迁移旧文件）。

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `index_tts_url` | `http://127.0.0.1:7860/` | IndexTTS Gradio 服务地址 |
| `lang_choice` | `ZH` | 合成语言；仅在服务提供此参数时发送，可选值以服务 API 为准 |
| `default_reference_audio` | 空 | 默认参考音频的**绝对路径**；留空则必须由用户设置个人音色 |
| `auto_capture_voice` | `false` | 自动把用户语音保存为音色；开启前请确认隐私告知 |
| `auto_tts_enabled` | `true` | 自动 TTS 的全局默认值，会话内可用 `/tts_auto` 覆盖 |
| `max_auto_tts_length` | `500` | 自动 TTS 的最大字符数 |
| `infer_mode` | `批次推理` | 仅对提供此参数的旧版接口生效 |
| `max_text_tokens_per_sentence` | `120` | 单句最大 token 数；新版自动映射为 `max_text_tokens_per_segment` |
| `sentences_bucket_max_size` | `4` | 批次推理分桶大小；仅对提供此参数的旧版接口生效 |
| `do_sample` | `true` | 是否采样 |
| `top_p` | `0.8` | 采样 top-p |
| `top_k` | `30` | 采样 top-k |
| `temperature` | `1.0` | 采样温度 |
| `length_penalty` | `0.0` | 长度惩罚 |
| `num_beams` | `3` | beam search 数量 |
| `repetition_penalty` | `10.0` | 重复惩罚 |
| `max_mel_tokens` | `600` | 最大 mel token 数 |

> 如果 AstrBot 运行在 Docker 中而 IndexTTS 在宿主机，通常把地址改为
> `http://host.docker.internal:7860/`；Linux 下可能需要额外的 `extra_hosts` 配置。

### API 兼容方式

- 首次连接读取 `view_api()`，只发送 `/gen_single` 实际接受的参数。
- 采样参数优先按接口标签（如 `top_p`）映射；已知接口缺少标签时，旧版使用
  `param_5` 至 `param_12`，带语言和时长控制的新版使用 `param_18` 至 `param_25`。
- 新版补齐语言、情感参考音频、情感权重、向量和时长参数。情感模式使用服务公布的
  第一个选项（官方 WebUI 的“与音色参考音频相同”），参考音频与音色参考一致，
  `emo_weight=0.65`、情感向量全零、`emo_random=false`、`duration_factor=1.0`。
- 旧配置中的采样值和分句长度继续生效，不需要手动改成 `param_18` 等 API 名称。
- 未识别的可选参数使用服务默认值；遇到未识别的必填参数会停止调用并在日志中说明，
  不通过反复生成音频来猜测接口。
- 支持字符串路径、Gradio `update.value`、`FileData.path` / `name` 以及首个输出的嵌套形式。
  生成文件必须已经由 Gradio 客户端下载到 AstrBot 可读的位置；仅返回服务端路径或 URL
  而本机无文件时会报错，不自动访问任意返回 URL。插件仅清理自己的生成目录，
  不删除 Gradio 返回的源文件。

接口字段可参考 [IndexTTS WebUI 源码](https://github.com/index-tts/index-tts/blob/main/webui.py)，
实际运行时以连接到的服务公布的 API 为准。

### AstrBot 调试

更新并重载插件后，先核对配置。例如 AstrBot 在 Docker、IndexTTS 在宿主机时：

```text
index_tts_url = http://host.docker.internal:7860/
default_reference_audio = /AstrBot/data/plugin_data/astrbot_plugin_indextts/voices/voice_03.wav
lang_choice = ZH
```

参考音频路径必须在 AstrBot 容器内存在；以上文件名仅为示例。网络已经打通时无需
为了本次 API 修复重新配置 Docker 网络或重新下载模型。

1. 在聊天中发送 `/tts_params`，核对参考音频与语言。首次生成前显示“未连接”是正常的，
   客户端采用懒连接；该状态也不代表实时健康检查。
2. 发送 `/tts 你好，这是新版接口兼容测试。`，检查是否收到可播放语音。
3. 日志应出现 `IndexTTS /gen_single 接口适配完成`，其中包含实际使用的参数名。
4. 手动合成成功后，发送 `/tts_auto on`，让 LLM 回复一段短文本，检查自动语音。

Docker 中可查看日志：

```bash
sudo docker logs --since 10m --tail 200 astrbot
```

连接、接口初始化和生成失败现在会记录完整异常链。请查看 Traceback 中最初的
`TypeError`、参数映射错误或服务端错误；聊天中的错误提示仍保持简短。
如果日志显示音频在 AstrBot 本机不可读，请检查 Gradio 客户端下载情况及返回格式。

### 旧版配置迁移

2.0.0 起配置迁移到 AstrBot 配置系统。首次启动时，如果检测到旧版
`data/config.json`，会尝试把已知键合并到新配置，并把旧文件重命名为
`config.json.migrated`。旧版 `data/voices/` 中的个人音色不会自动迁移，需要
用户重新发送 `/tts_voice` 设置。

## 数据与隐私

- 持久化数据位于 AstrBot 的 `data/plugin_data/astrbot_plugin_indextts/`：
  - `voices/`：个人参考音频；
  - `generated/`：生成的语音，自动保留最近 50 个。
- 插件**不再内置示例音色**。未设置参考音频时，`/tts` 会提示先设置，自动 TTS 会安静跳过。
- 语音属于敏感数据；插件会尽量把音色目录设为仅当前用户可访问，并只把音频发送到用户配置的 IndexTTS 服务。
- 自动捕获语音默认关闭。开启前请向用户说明并取得同意。

## 安全说明

- `/tts_voice` 的 URL 仅允许 **公网 HTTP(S)** 音频；拒绝私有地址、回环地址、带凭据 URL 和重定向。
- 下载大小上限 10MB，并校验文件头（WAV/MP3/OGG/FLAC/M4A/AMR/SILK）。
- 服务器本地文件路径仅 **管理员** 可用；普通用户只能使用 URL 或语音消息。
- 用户 ID 经过 SHA-256 哈希后作为文件名，避免路径穿越、空 ID 和平台字符差异。
- 音色/生成音频使用临时文件 + `os.replace` 原子写入，失败不会破坏旧文件。
- 错误信息不会把服务器路径或完整异常直接返回给普通用户。

## 开发

```bash
python -m unittest discover -s tests -t . -v
ruff check .
```

项目使用 Ruff 配置（`pyproject.toml`）和 GitHub Actions CI。

`tests/test_client.py` 覆盖新旧 API 的参数契约、语言选项、未知必填参数、返回格式、
生成文件保存和错误链；通过真实 `gradio_client` 参数绑定函数验证调用参数。
这些测试模拟网络和推理，不替代 AstrBot、IndexTTS 和消息平台的端到端语音验证。

## 许可证

本插件代码使用 MIT License，见 [LICENSE](LICENSE)。IndexTTS、AstrBot 及其依赖分别遵循各自许可证；使用和分发时请一并遵守。
