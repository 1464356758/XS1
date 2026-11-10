"""可选实库接线测试；冻结仅发生于临时合成作品，不评价文学质量。"""
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import novel_library as library
import novel_state as workspace
import reference_bridge as bridge
from test_narrative_quality import QualityFixture


@unittest.skipUnless(os.environ.get("NOVEL_XSKU_ROOT"), "需要显式提供实库检出目录")
class RealLibraryIntegration(QualityFixture):
    def test_all_registered_evidence_and_actual_packet_reach_frozen_synthetic_chapter(self):
        source_root = Path(os.environ["NOVEL_XSKU_ROOT"]).resolve()
        before = (source_root / "catalog.json").read_bytes()
        catalog = library.load(source_root); origin = bridge.checkout_origin(source_root)
        all_packet = self.root.parent / "all-lessons.json"
        library.export_packet(source_root, list(catalog["studies"]), list(catalog["reviews"]),
                              "实库来源校验，不作文学评价", all_packet, **origin)
        self.assertEqual(len(workspace.read_json(all_packet)["lessons"]), len(catalog["studies"]) + len(catalog["reviews"]))
        workspace.atomic_json(self.root.parent / "project_config.json", {"reference_library": {
            "repository_url": origin["repository_url"], "library_id": catalog["library_id"], "require_source_locations": True}})
        packet_path = self.root.parent / "packet.json"
        bridge.prepare(self.root.parent, source_root, "关系 主动选择", packet_path)
        requested = self.root.parent / "requested.json"
        self.q.request_brief(self.root, requested, self.a, packet_path)
        _, brief = self.brief()
        brief["references"] = workspace.read_json(requested)["references"]
        brief["references"].update(application="合成机制验证：交出钥匙导致此后无法自由出门。",
                                    originality="合成作品仅使用测试角色及独立的守门后果，不移植参考原作事件。")
        workspace.atomic_json(requested, brief); self.q.check_brief(self.root, requested, self.a)
        writer = workspace.context(self.root, profile="writer")
        self.assertIn("无法自由出门", writer); self.assertNotIn(origin["repository_url"], writer)
        with patch.object(self, "register_brief", return_value=(None, brief)):
            draft, rec, _, report = self.prepare(1)
        report["narrative_review"]["reference_use"].update(
            outcome="adapted", application_observed="合成正文用交接钥匙测试选择后果及引用字段。",
            originality_review="本次只核接线与版本，不声称已验证文学效果或签约。",
            evidence=[{"chapter": 1, "sha256": workspace.digest(draft.read_text()),
                       "quote": draft.read_text().split("。")[0] + "。"}])
        self.gate(draft, rec, report); workspace.adopt(self.root, draft, rec)
        frozen = workspace.load_state(self.root)["serialization"]["frozen"]
        self.assertIn("1", frozen)
        self.assertEqual(before, (source_root / "catalog.json").read_bytes())


if __name__ == "__main__": unittest.main()
