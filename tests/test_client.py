# SPDX-License-Identifier: MIT
"""Regression tests for legacy and multilingual IndexTTS Gradio APIs.

The multilingual signature follows the successful /gen_single call from the
deployment diagnosis and index-tts/index-tts webui.py. Networking and GPU work
are mocked; Gradio's real argument binder and file helper are exercised.
"""

from __future__ import annotations

import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

from gradio_client.utils import construct_args

from core.api import GenSingleAPI
from core.client import IndexTTSClient, TTSError, TTSServiceUnavailable
from core.config import DEFAULT_CONFIG

SAMPLING = [
    "do_sample",
    "top_p",
    "top_k",
    "temperature",
    "length_penalty",
    "num_beams",
    "repetition_penalty",
    "max_mel_tokens",
]


def endpoint(*, modern: bool = True, labels: bool = True, offset: int | None = None) -> dict:
    if modern:
        names = [
            "emo_control_method",
            "prompt",
            "text",
            "lang_choice",
            "emo_ref_path",
            "emo_weight",
            "vec1",
            "vec2",
            "vec3",
            "vec4",
            "vec5",
            "vec6",
            "vec7",
            "vec8",
            "emo_text",
            "emo_random",
            "max_text_tokens_per_segment",
            "duration_factor",
        ]
    else:
        names = [
            "prompt",
            "text",
            "infer_mode",
            "max_text_tokens_per_sentence",
            "sentences_bucket_max_size",
        ]
    start = len(names) if offset is None else offset
    parameters = [{"parameter_name": name, "parameter_has_default": False} for name in names]
    for i, key in enumerate(SAMPLING):
        parameter = {"parameter_name": f"param_{start + i}", "parameter_has_default": False}
        if labels:
            parameter["label"] = key
        parameters.append(parameter)
    return {"parameters": parameters}


class APIMappingTests(unittest.TestCase):
    def test_modern_api_maps_all_values_and_omits_legacy_only_fields(self) -> None:
        schema = endpoint()
        config = {
            **DEFAULT_CONFIG,
            "lang_choice": "EN",
            "max_text_tokens_per_sentence": 88,
            "do_sample": False,
            "top_p": 0.6,
            "top_k": 17,
            "temperature": 0.7,
            "length_penalty": -0.5,
            "num_beams": 2,
            "repetition_penalty": 8.0,
            "max_mel_tokens": 900,
        }
        audio = {"path": "reference.wav"}
        kwargs = GenSingleAPI(schema).build_kwargs(config, "hello", audio)
        self.assertEqual(set(kwargs), {p["parameter_name"] for p in schema["parameters"]})
        self.assertEqual(kwargs["max_text_tokens_per_segment"], 88)
        self.assertEqual(kwargs["lang_choice"], "EN")
        self.assertIs(kwargs["prompt"], audio)
        self.assertIs(kwargs["emo_ref_path"], audio)
        self.assertEqual(kwargs["emo_control_method"], "与音色参考音频相同")
        self.assertEqual(kwargs["duration_factor"], 1.0)
        self.assertEqual(kwargs["emo_weight"], 0.65)
        self.assertEqual([kwargs[f"vec{i}"] for i in range(1, 9)], [0.0] * 8)
        self.assertEqual(kwargs["emo_text"], "")
        self.assertIs(kwargs["emo_random"], False)
        expected = [False, 0.6, 17, 0.7, -0.5, 2, 8.0, 900]
        self.assertEqual([kwargs[f"param_{i}"] for i in range(18, 26)], expected)
        self.assertEqual(construct_args(schema["parameters"], (), kwargs)[18:], expected)

    def test_legacy_api_keeps_original_parameter_contract(self) -> None:
        schema = endpoint(modern=False)
        kwargs = GenSingleAPI(schema).build_kwargs({"top_k": 42}, "你好", "audio")
        self.assertEqual(kwargs["param_7"], 42)
        self.assertEqual(kwargs["infer_mode"], "批次推理")
        self.assertEqual(kwargs["max_text_tokens_per_sentence"], 120)
        self.assertEqual(kwargs["sentences_bucket_max_size"], 4)
        self.assertEqual(len(kwargs), 13)
        self.assertEqual(len(construct_args(schema["parameters"], (), kwargs)), 13)

    def test_known_signatures_work_without_sampling_labels(self) -> None:
        for modern, top_k_name in ((True, "param_20"), (False, "param_7")):
            with self.subTest(modern=modern):
                schema = endpoint(modern=modern, labels=False)
                kwargs = GenSingleAPI(schema).build_kwargs({"top_k": 43}, "text", "audio")
                self.assertEqual(kwargs[top_k_name], 43)
                construct_args(schema["parameters"], (), kwargs)

    def test_labels_follow_changed_numbering_and_take_precedence(self) -> None:
        schema = endpoint(offset=40)
        kwargs = GenSingleAPI(schema).build_kwargs({"temperature": 0.4}, "text", "audio")
        self.assertEqual(kwargs["param_43"], 0.4)
        schema = endpoint()
        schema["parameters"][18]["label"] = "top_k"
        kwargs = GenSingleAPI(schema).build_kwargs({"top_k": 21}, "text", "audio")
        self.assertEqual(kwargs["param_18"], 21)

    def test_named_sampling_parameters(self) -> None:
        schema = endpoint()
        for parameter, name in zip(schema["parameters"][18:], SAMPLING, strict=True):
            parameter["parameter_name"] = name
        kwargs = GenSingleAPI(schema).build_kwargs({"top_p": 0.3}, "text", "audio")
        self.assertEqual(kwargs["top_p"], 0.3)
        construct_args(schema["parameters"], (), kwargs)

    def test_unknown_optional_parameter_uses_server_default(self) -> None:
        schema = endpoint()
        schema["parameters"].append(
            {
                "parameter_name": "future_option",
                "parameter_has_default": True,
                "parameter_default": 7,
            }
        )
        kwargs = GenSingleAPI(schema).build_kwargs({}, "text", "audio")
        self.assertNotIn("future_option", kwargs)
        self.assertEqual(construct_args(schema["parameters"], (), kwargs)[-1], 7)

    def test_unknown_required_parameter_fails_before_prediction(self) -> None:
        schema = endpoint()
        schema["parameters"].append({"parameter_name": "new_required_option"})
        with self.assertRaisesRegex(ValueError, "new_required_option"):
            GenSingleAPI(schema)

    def test_invalid_schema_fails_clearly(self) -> None:
        for schema in (
            {},
            {"parameters": []},
            {"parameters": [{}]},
            {"parameters": [{"parameter_name": "prompt"}]},
        ):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                GenSingleAPI(schema)

    def test_localized_emotion_choice_and_language_validation(self) -> None:
        schema = endpoint()
        schema["parameters"][0]["type"] = {"enum": ["Same as speaker reference", "Other"]}
        schema["parameters"][3]["type"] = {"enum": ["ZH", "EN"]}
        api = GenSingleAPI(schema)
        self.assertEqual(
            api.build_kwargs({}, "text", "audio")["emo_control_method"], "Same as speaker reference"
        )
        with self.assertRaisesRegex(ValueError, "lang_choice"):
            api.build_kwargs({"lang_choice": "INVALID"}, "text", "audio")

    def test_config_defaults_match_webui_schema(self) -> None:
        schema_path = Path(__file__).resolve().parents[1] / "_conf_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(DEFAULT_CONFIG, {key: item["default"] for key, item in schema.items()})


class ResultPathTests(unittest.TestCase):
    def test_supported_result_shapes(self) -> None:
        name = str(Path("cache") / "speech.wav")
        for result in (
            name,
            Path(name),
            {"value": name, "__type__": "update"},
            {"path": name},
            {"name": name},
            {"value": {"path": name}},
            ({"value": {"path": name}}, "status"),
            [name],
        ):
            with self.subTest(result=result):
                self.assertEqual(IndexTTSClient._result_path(result), Path(name))

    def test_invalid_results_and_remote_urls_are_not_local_files(self) -> None:
        for result in (
            None,
            "",
            "  ",
            [],
            (),
            {},
            {"visible": False},
            3,
            {"value": 42},
            "https://example.com/audio.wav",
            {"url": "https://example.com/audio.wav"},
        ):
            with self.subTest(result=result):
                self.assertIsNone(IndexTTSClient._result_path(result))


def write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(b"\x00\x00" * 100)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.reference = self.root / "reference.wav"
        self.generated = self.root / "generated.wav"
        write_wav(self.reference)
        write_wav(self.generated)
        self.client = IndexTTSClient(
            "http://localhost:7860", self.root / "out", {**DEFAULT_CONFIG, "top_k": 23}
        )
        self.addAsyncCleanup(self.client.close)
        self.remote = Mock()
        self.schema = endpoint()
        self.remote.view_api.return_value = {"named_endpoints": {"/gen_single": self.schema}}
        self.remote.predict.return_value = {"value": {"path": str(self.generated)}}
        factory_patch = patch("core.client.Client", return_value=self.remote)
        self.addCleanup(factory_patch.stop)
        self.client_factory = factory_patch.start()
        http_patch = patch("core.client.httpx.Client")
        self.addCleanup(http_patch.stop)
        http_patch.start()

    async def test_generate_adapts_api_and_atomically_saves_audio(self) -> None:
        output = await self.client.generate("你好", self.reference)
        self.assertEqual(output.parent, self.root / "out")
        self.assertEqual(output.read_bytes(), self.generated.read_bytes())
        self.assertTrue(self.reference.is_file())
        self.assertTrue(self.generated.is_file())
        self.assertFalse(list(output.parent.glob("*.part")))
        self.client_factory.assert_called_once_with("http://localhost:7860/", verbose=False)
        self.remote.view_api.assert_called_once_with(return_format="dict", print_info=False)
        kwargs = self.remote.predict.call_args.kwargs.copy()
        self.assertEqual(kwargs.pop("api_name"), "/gen_single")
        self.assertEqual(kwargs["prompt"]["path"], str(self.reference))
        self.assertEqual(kwargs["emo_ref_path"], kwargs["prompt"])
        self.assertEqual(kwargs["param_20"], 23)
        construct_args(self.schema["parameters"], (), kwargs)
        await self.client.generate("再次生成", self.reference)
        self.remote.view_api.assert_called_once()

    async def test_legacy_generate_also_works(self) -> None:
        self.schema = endpoint(modern=False)
        self.remote.view_api.return_value = {"named_endpoints": {"/gen_single": self.schema}}
        await self.client.generate("你好", self.reference)
        kwargs = self.remote.predict.call_args.kwargs.copy()
        kwargs.pop("api_name")
        self.assertEqual(kwargs["param_7"], 23)
        construct_args(self.schema["parameters"], (), kwargs)

    async def test_unsupported_api_closes_client_and_preserves_cause(self) -> None:
        self.schema["parameters"].append({"parameter_name": "unknown_required"})
        with self.assertRaises(TTSServiceUnavailable) as caught:
            await self.client.generate("你好", self.reference)
        self.assertIn("unknown_required", str(caught.exception.__cause__))
        self.remote.close.assert_called_once()
        self.remote.predict.assert_not_called()
        with self.assertRaises(TTSServiceUnavailable):
            await self.client.generate("你好", self.reference)
        self.client_factory.assert_called_once()

    async def test_missing_endpoint_closes_client(self) -> None:
        self.remote.view_api.return_value = {"named_endpoints": {}}
        with self.assertRaises(TTSServiceUnavailable) as caught:
            await self.client.generate("你好", self.reference)
        self.assertIn("/gen_single", str(caught.exception.__cause__))
        self.remote.close.assert_called_once()
        self.remote.predict.assert_not_called()

    async def test_prediction_failure_preserves_original_traceback_cause(self) -> None:
        failure = TypeError("unexpected keyword argument")
        self.remote.predict.side_effect = failure
        with self.assertRaises(TTSError) as caught:
            await self.client.generate("你好", self.reference)
        self.assertIs(caught.exception.__cause__, failure)
        self.assertFalse(self.client.is_connected)
        self.remote.close.assert_called_once()

    async def test_missing_or_invalid_generated_file_does_not_create_output(self) -> None:
        invalid = self.root / "invalid.wav"
        invalid.write_text("not audio", encoding="utf-8")
        for result in ({"value": str(self.root / "missing.wav")}, {"path": str(invalid)}):
            self.remote.predict.return_value = result
            with self.assertRaises(TTSError):
                await self.client.generate("你好", self.reference)
            self.assertFalse(list((self.root / "out").glob("tts_*.wav")))

    async def test_failed_save_preserves_source_and_cleans_partial_file(self) -> None:
        with patch("core.client.os.replace", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(TTSError, "保存"):
                await self.client.generate("你好", self.reference)
        self.assertTrue(self.generated.is_file())
        self.assertEqual(list((self.root / "out").iterdir()), [])
