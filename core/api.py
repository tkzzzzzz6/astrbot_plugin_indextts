# SPDX-License-Identifier: MIT
"""Map stable plugin settings onto the server's Gradio /gen_single schema."""

from __future__ import annotations

from typing import Any

from .config import DEFAULT_CONFIG

SAMPLING_PARAMS = (
    "do_sample",
    "top_p",
    "top_k",
    "temperature",
    "length_penalty",
    "num_beams",
    "repetition_penalty",
    "max_mel_tokens",
)
DIRECT_PARAMS = {
    "prompt",
    "text",
    "infer_mode",
    "max_text_tokens_per_sentence",
    "sentences_bucket_max_size",
    "lang_choice",
    "emo_control_method",
    "emo_ref_path",
    "emo_weight",
    "emo_text",
    "emo_random",
    "duration_factor",
    *(f"vec{i}" for i in range(1, 9)),
    *SAMPLING_PARAMS,
}


class GenSingleAPI:
    """Resolve parameter names once per connection, without trial synthesis."""

    def __init__(self, endpoint: dict[str, Any]) -> None:
        parameters = endpoint.get("parameters")
        if not isinstance(parameters, list) or not parameters:
            raise ValueError("/gen_single 缺少参数定义，请检查 Gradio API 信息")
        self.parameters: dict[str, dict[str, Any]] = {}
        for parameter in parameters:
            name = parameter.get("parameter_name") if isinstance(parameter, dict) else None
            if not isinstance(name, str) or not name or name in self.parameters:
                raise ValueError("/gen_single 参数定义无效或包含重复名称")
            self.parameters[name] = parameter
        names = self.parameters.keys()
        if not {"prompt", "text"} <= names:
            raise ValueError("/gen_single 缺少 prompt 或 text 参数")

        # Older Gradio releases may omit labels. Only use numbered fallbacks
        # for the known legacy and multilingual (2.5) signatures. Otherwise
        # labels such as 'top_p' identify the meaning regardless of numbering.
        fallback: dict[str, str] = {}
        if {"infer_mode", "max_text_tokens_per_sentence", "sentences_bucket_max_size"} <= names:
            start = 5
        elif {
            "lang_choice",
            "emo_control_method",
            "max_text_tokens_per_segment",
            "duration_factor",
        } <= names:
            start = 18
        else:
            start = None
        if start is not None and {f"param_{start + i}" for i in range(8)} <= names:
            fallback = {f"param_{start + i}": key for i, key in enumerate(SAMPLING_PARAMS)}

        self.mapping: dict[str, str] = {}
        unsupported = []
        for name, parameter in self.parameters.items():
            label = str(parameter.get("label") or "").strip()
            if name in DIRECT_PARAMS:
                self.mapping[name] = name
            elif name == "max_text_tokens_per_segment":
                self.mapping[name] = "max_text_tokens_per_sentence"
            elif name.startswith("param_") and label in SAMPLING_PARAMS:
                self.mapping[name] = label
            elif name in fallback:
                self.mapping[name] = fallback[name]
            elif not parameter.get("parameter_has_default", False):
                unsupported.append(name)
        if unsupported:
            raise ValueError("/gen_single 存在无法映射的必填参数: " + ", ".join(unsupported))

    def build_kwargs(
        self,
        params: dict[str, Any],
        text: str,
        audio: Any,
    ) -> dict[str, Any]:
        values = {**DEFAULT_CONFIG, **params}
        values.update(
            {
                "prompt": audio,
                "text": text,
                # The first official emotion choice means 'same as speaker'. Use
                # its advertised value so both Chinese and English WebUIs work.
                "emo_control_method": "与音色参考音频相同",
                "emo_ref_path": audio,
                "emo_weight": 0.65,
                "emo_text": "",
                "emo_random": False,
                "duration_factor": 1.0,
                **{f"vec{i}": 0.0 for i in range(1, 9)},
            }
        )
        emotion_type = self.parameters.get("emo_control_method", {}).get("type", {})
        choices = emotion_type.get("enum") if isinstance(emotion_type, dict) else None
        if isinstance(choices, list) and choices:
            values["emo_control_method"] = choices[0]

        kwargs = {name: values[key] for name, key in self.mapping.items()}
        for name, value in kwargs.items():
            schema = self.parameters[name].get("type", {})
            choices = schema.get("enum") if isinstance(schema, dict) else None
            if isinstance(choices, list) and choices and value not in choices:
                raise ValueError(f"/gen_single 参数 {name} 的配置值不在服务支持的选项中")
        return kwargs
