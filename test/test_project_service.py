import unittest

from models import FactorItem, ProjectData, ResponseItem
from services.project_service import ProjectService, signature


class ProjectServiceTests(unittest.TestCase):
    def make_project(self):
        return ProjectData(
            factors=[FactorItem(
                name="A", param1="0", param2="1")],
            responses=[ResponseItem(name="Y")],
            design_method="两水平筛选设计",
            doe_matrix=[{"Run_ID": 1, "A": 0.0, "Y": ""}],
            screening_result={"old": True},
            workbench_result={"old": True},
        )

    def test_definition_change_invalidates_results_and_copies_input(self):
        project = self.make_project()
        service = ProjectService.for_project(project)
        factors = [FactorItem(name="B", param1="-1", param2="1")]
        responses = [ResponseItem(name="Z")]

        changed = service.update_definition(factors, responses)
        factors[0].name = "mutated outside"

        self.assertTrue(changed)
        self.assertEqual(project.factors[0].name, "B")
        self.assertEqual(project.responses[0].name, "Z")
        self.assertEqual(project.screening_result, {})
        self.assertEqual(project.workbench_result, {})

    def test_invalid_response_update_is_atomic(self):
        project = self.make_project()
        service = ProjectService.for_project(project)
        original_matrix = [dict(row) for row in project.doe_matrix]
        original_result = dict(project.screening_result)

        with self.assertRaisesRegex(ValueError, "必须是数字"):
            service.update_responses([
                {"Run_ID": "1", "A": "0", "Y": "invalid"}])

        self.assertEqual(project.doe_matrix, original_matrix)
        self.assertEqual(project.screening_result, original_result)

    def test_stale_async_result_is_rejected(self):
        project = self.make_project()
        service = ProjectService.for_project(project)
        started_from = signature(project)
        project.doe_matrix[0]["A"] = 0.5

        with self.assertRaisesRegex(ValueError, "输入已改变"):
            service.publish_results(
                expected_signature=started_from,
                workbench_result={"candidate": 1})

        self.assertEqual(project.workbench_result, {"old": True})


if __name__ == "__main__":
    unittest.main()
