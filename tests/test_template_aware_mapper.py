from __future__ import annotations

import unittest

from app.config import PipelineConfig
from app.models import AssetPackage, MatchedProperty, ModelInfo
from modules.aas_mapping import TemplateAwareAASMapper


class _FakePlacementLLM:
    def generate_json(self, prompt: str, fallback: dict | None = None) -> dict:
        return {
            "selected_submodel": "DigitalNameplate",
            "confidence": 0.93,
            "review_required": False,
            "reason": "manufacturer identity belongs to the nameplate submodel",
        }


class TemplateAwareMapperTest(unittest.TestCase):
    def test_llm_template_selector_can_correct_submodel(self) -> None:
        config = PipelineConfig()
        mapper = TemplateAwareAASMapper(
            default_submodels_path=config.project_root
            / "repositories"
            / "submodel_templates"
            / "default_submodels.json",
            template_root=config.project_root
            / "repositories"
            / "submodel_templates"
            / "admin_shell_io_submodel_templates"
            / "published",
            llm_client=_FakePlacementLLM(),
            use_llm_template_selection=True,
        )
        asset = AssetPackage(
            asset_id="asset-a",
            asset_name="Asset A",
            asset_type="robot_arm",
            manufacturer="ROBOTIS",
        )
        matched = [
            MatchedProperty(
                semantic_node_id="SN_001",
                aas_property_id="AAS_PROP_MANUFACTURER",
                submodel="TechnicalData",
                idShort="ManufacturerName",
                value="ROBOTIS",
                unit=None,
                match_score=0.91,
                semantic_id="0112/2///61987#ABA565#009",
                eclass_irdi="0173-1#02-AAO677#004",
                source="project_repository",
                definition="Name of the manufacturer responsible for the product.",
            )
        ]
        model = ModelInfo(
            model_path="data/generated_models/asset-a.glb",
            model_format="glb",
            generation_method="existing",
        )

        plan = mapper.map(asset, matched, model)

        digital_nameplate = next(
            item for item in plan["submodels"] if item["idShort"] == "DigitalNameplate"
        )
        id_shorts = {item["idShort"] for item in digital_nameplate["properties"]}
        self.assertIn("ManufacturerName", id_shorts)
        self.assertEqual("DigitalNameplate", matched[0].submodel)

    def test_technical_property_definition_does_not_force_nameplate(self) -> None:
        config = PipelineConfig()
        mapper = TemplateAwareAASMapper(
            default_submodels_path=config.project_root
            / "repositories"
            / "submodel_templates"
            / "default_submodels.json",
            template_root=config.project_root
            / "repositories"
            / "submodel_templates"
            / "admin_shell_io_submodel_templates"
            / "published",
        )
        asset = AssetPackage(
            asset_id="asset-a",
            asset_name="Asset A",
            asset_type="robot_arm",
            manufacturer="ROBOTIS",
        )
        matched = [
            MatchedProperty(
                semantic_node_id="SN_002",
                aas_property_id="0173-1#02-AAF583#004",
                submodel="DigitalNameplate",
                idShort="NominalVoltage",
                value="24",
                unit="V",
                match_score=0.95,
                semantic_id="0173-1#02-AAF583#004",
                eclass_irdi="0173-1#02-AAF583#004",
                source="eclass_dictionary",
                definition=(
                    "Information on the rated voltage of the product according to "
                    "the manufacturer or supplier."
                ),
            )
        ]
        model = ModelInfo(
            model_path="data/generated_models/asset-a.glb",
            model_format="glb",
            generation_method="existing",
        )

        plan = mapper.map(asset, matched, model)

        technical_data = next(
            item for item in plan["submodels"] if item["idShort"] == "TechnicalData"
        )
        digital_nameplate = next(
            item for item in plan["submodels"] if item["idShort"] == "DigitalNameplate"
        )
        self.assertIn(
            "NominalVoltage",
            {item["idShort"] for item in technical_data["properties"]},
        )
        self.assertNotIn(
            "NominalVoltage",
            {item["idShort"] for item in digital_nameplate["properties"]},
        )
        self.assertEqual("TechnicalData", matched[0].submodel)


if __name__ == "__main__":
    unittest.main()
