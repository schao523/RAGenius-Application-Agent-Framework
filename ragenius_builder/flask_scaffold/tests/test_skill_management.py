from __future__ import annotations

import shutil
import os
import sys
import unittest
import zipfile
import importlib
import json
import io
from pathlib import Path
from uuid import uuid4


SCAFFOLD_DIR = Path(__file__).resolve().parents[1]
if str(SCAFFOLD_DIR) not in sys.path:
    sys.path.insert(0, str(SCAFFOLD_DIR))
os.environ["RAGENIUS_BUILDER_DISABLE_GLOBAL_STORE"] = "1"

from storage import DatabaseStore  # noqa: E402


def _make_skill_archive(base_dir: Path, *, version: str = "1.0.0") -> Path:
    src = base_dir / "skill_src"
    (src / "references").mkdir(parents=True)
    (src / "workflows").mkdir(parents=True)
    (src / "schemas").mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: lesson_planner_skill",
                "name: Lesson Planner Skill",
                f"version: {version}",
                "description: Generate a lesson plan from source material.",
                "required_tools:",
                "  - rag_retrieval_tool",
                "required_permissions:",
                "  - rag.read",
                "workflow_ref: workflows/lesson-plan.json",
                "input_schema_ref: schemas/input.schema.json",
                "output_schema_ref: schemas/output.schema.json",
                "---",
                "",
                "# Lesson Planner Skill",
            ]
        ),
        encoding="utf-8",
    )
    (src / "workflows" / "lesson-plan.json").write_text(
        '{"steps":[{"id":"retrieve_context","type":"tool_call","toolId":"rag_retrieval_tool","inputMapping":{"query":"$.input.topic","topK":3},"outputMapping":{"items":"$.output.items"},"on":{"success":"finish"}},{"id":"finish","type":"end"}]}',
        encoding="utf-8",
    )
    (src / "schemas" / "input.schema.json").write_text(
        '{"type":"object","properties":{"topic":{"type":"string"}},"required":["topic"]}',
        encoding="utf-8",
    )
    (src / "schemas" / "output.schema.json").write_text(
        '{"type":"object","properties":{"summary":{"type":"string"}},"required":["summary"]}',
        encoding="utf-8",
    )
    (src / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    archive_path = base_dir / "lesson_planner_skill.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in src.rglob("*"):
            archive.write(path, path.relative_to(src))
    return archive_path


def _make_codex_style_skill_archive(base_dir: Path) -> Path:
    src = base_dir / "codex_skill_src"
    (src / "references").mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "name: Retrieval Coach",
                "description: Help users refine retrieval prompts.",
                "---",
                "",
                "# Retrieval Coach",
            ]
        ),
        encoding="utf-8",
    )
    (src / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")

    archive_path = base_dir / "retrieval_coach_skill.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in src.rglob("*"):
            archive.write(path, path.relative_to(src))
    return archive_path


def _make_execution_ready_skill_archive(base_dir: Path) -> Path:
    src = base_dir / "execution_ready_skill_src"
    (src / "workflows").mkdir(parents=True)
    (src / "schemas").mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: research_paper_finder",
                "name: research-paper-finder",
                "version: 1.0.0",
                "description: Find and summarize top research papers for a topic.",
                "required_tools:",
                "  - research_paper_search_tool",
                "required_permissions:",
                "  - external_api.read",
                "workflow_ref: workflows/research-paper-finder.json",
                "input_schema_ref: schemas/input.schema.json",
                "output_schema_ref: schemas/output.schema.json",
                "---",
                "",
                "# Research Paper Finder",
            ]
        ),
        encoding="utf-8",
    )
    (src / "workflows" / "research-paper-finder.json").write_text(
        json.dumps(
            {
                "steps": [
                    {
                        "id": "search_papers",
                        "type": "tool_call",
                        "toolId": "research_paper_search_tool",
                        "inputMapping": {
                            "topic": "$.input.topic",
                            "limit": "$.input.limit",
                            "source": "$.input.source",
                        },
                        "outputMapping": {
                            "topic": "$.output.topic",
                            "source": "$.output.source",
                            "papers": "$.output.papers",
                        },
                        "on": {"success": "finish"},
                    },
                    {"id": "finish", "type": "end"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (src / "schemas" / "input.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "limit": {"type": "integer"},
                    "source": {
                        "type": "string",
                        "enum": ["auto", "arxiv", "semantic-scholar"],
                    },
                },
                "required": ["topic"],
            }
        ),
        encoding="utf-8",
    )
    (src / "schemas" / "output.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "topic": {"type": "string"},
                    "source": {"type": "string"},
                    "papers": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string"},
                                "link": {"type": "string"},
                                "year": {"type": "integer"},
                                "authors": {"type": "array", "items": {"type": "string"}},
                                "summary": {"type": "string"},
                                "why_it_matters": {"type": "string"},
                            },
                            "required": [
                                "title",
                                "link",
                                "year",
                                "authors",
                                "summary",
                                "why_it_matters",
                            ],
                        },
                    },
                },
                "required": ["topic", "source", "papers"],
            }
        ),
        encoding="utf-8",
    )

    archive_path = base_dir / "research_paper_finder.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in src.rglob("*"):
            archive.write(path, path.relative_to(src))
    return archive_path


def _make_descriptive_skill_archive(
    base_dir: Path,
    *,
    folder_name: str,
    archive_name: str,
    skill_name: str,
    description: str,
    body_lines: list[str],
) -> Path:
    src = base_dir / folder_name
    src.mkdir(parents=True, exist_ok=True)
    (src / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                f"name: {skill_name}",
                f"description: {description}",
                "---",
                "",
                *body_lines,
            ]
        ),
        encoding="utf-8",
    )
    archive_path = base_dir / archive_name
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(src / "SKILL.md", "SKILL.md")
    return archive_path


def _make_research_paper_skill_markdown_only_archive(base_dir: Path) -> Path:
    src = base_dir / "research_paper_markdown_only_src"
    src.mkdir(parents=True, exist_ok=True)
    (src / "SKILL.md").write_text(
        "\n".join(
            [
                "---",
                "id: topic_research_paper_finder",
                "name: topic-research-paper-finder",
                "version: 1.0.0",
                "description: Find and summarize top research papers for a user-defined topic using research_paper_search_tool.",
                "required_tools:",
                "  - research_paper_search_tool",
                "required_permissions:",
                "  - external_api.read",
                "---",
                "",
                "Topic Research Paper Finder",
                "",
                "## Tool Contract",
                "",
                "Call `research_paper_search_tool` using:",
                "    {",
                '      "topic": "string",',
                '      "limit": 5,',
                '      "source": "auto"',
                "    }",
                "",
                "Supported inputs:",
                "",
                "* `topic` (required)",
                "* `limit` (optional, range 1-10)",
                "* `source` (optional: `auto`, `arxiv`, `semantic-scholar`)",
                "",
                "Expected response:",
                "    {",
                '      "topic": "string",',
                '      "source": "string",',
                '      "papers": [',
                "        {",
                '          "title": "string",',
                '          "link": "string",',
                '          "year": "integer",',
                '          "authors": ["string"],',
                '          "summary": "string",',
                '          "why_it_matters": "string"',
                "        }",
                "      ]",
                "    }",
            ]
        ),
        encoding="utf-8",
    )
    archive_path = base_dir / "topic_research_paper_finder.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.write(src / "SKILL.md", "SKILL.md")
    return archive_path


class SkillManagementTests(unittest.TestCase):
    def setUp(self) -> None:
        base_dir = Path.cwd() / "outputs" / "builder_skill_tests"
        base_dir.mkdir(parents=True, exist_ok=True)
        self._tmpdir = base_dir / f"case_{uuid4().hex}"
        self._tmpdir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_database_store_creates_skill_management_tables(self) -> None:
        db_path = self._tmpdir / "builder.db"
        storage_root = self._tmpdir / "builder_storage"

        store = DatabaseStore(":memory:", storage_root=storage_root, seed_data=False)
        try:
            tables = {
                row["name"]
                for row in store.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            store.close()

        self.assertIn("skills", tables)
        self.assertIn("skill_versions", tables)
        self.assertIn("app_skill_bindings", tables)

    def test_import_skill_package_persists_versioned_skill_metadata(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = _make_skill_archive(self._tmpdir)
        skills_root = self._tmpdir / "managed_skills"

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=skills_root,
                scope="managed",
                import_source="upload",
            )
        finally:
            store.close()

        self.assertEqual(imported["skill"]["slug"], "lesson-planner-skill")
        self.assertEqual(imported["version"]["version"], "1.0.0")
        self.assertEqual(imported["version"]["state"], "draft")
        self.assertEqual(imported["version"]["validation_status"], "passed")
        self.assertTrue(
            (
                skills_root
                / "managed"
                / "lesson_planner_skill"
                / "1.0.0"
                / "SKILL.md"
            ).is_file()
        )

    def test_import_skill_package_rejects_missing_skill_manifest(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = self._tmpdir / "broken_skill.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr("references/guide.md", "# missing manifest\n")

        try:
            with self.assertRaisesRegex(ValueError, "SKILL.md"):
                store.import_skill_package(
                    archive_path=archive_path,
                    storage_root=self._tmpdir / "managed_skills",
                    scope="managed",
                    import_source="upload",
                )
        finally:
            store.close()

    def test_import_skill_package_accepts_codex_style_skill_frontmatter(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = _make_codex_style_skill_archive(self._tmpdir)
        skills_root = self._tmpdir / "managed_skills"

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=skills_root,
                scope="managed",
                import_source="upload",
            )
        finally:
            store.close()

        self.assertEqual(imported["skill"]["id"], "retrieval_coach")
        self.assertEqual(imported["skill"]["slug"], "retrieval-coach")
        self.assertEqual(imported["skill"]["name"], "Retrieval Coach")
        self.assertEqual(imported["version"]["version"], "1.0.0")
        self.assertTrue(
            (
                skills_root
                / "managed"
                / "retrieval_coach"
                / "1.0.0"
                / "SKILL.md"
            ).is_file()
        )

    def test_publish_bind_and_read_execution_ready_skill_contract(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = _make_skill_archive(self._tmpdir, version="2.0.0")
        app_payload = {
            "name": "Skill Test App",
            "slug": "skill-test-app",
            "description": "App for builder skill binding tests.",
            "starter_questions": ["one", "two", "three", "four"],
            "instructions": "# hi",
            "version": "v1",
        }

        try:
            created_app = store.create_application(app_payload)
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            published = store.publish_skill_version(imported["version"]["id"])
            binding = store.create_app_skill_binding(
                app_id=created_app["id"],
                skill_id=imported["skill"]["id"],
                skill_version=published["version"],
                permission_mode="require_confirmation",
                execution_policy={"allowAsync": False},
            )
            published_payload = store.get_published_skill_definition(
                skill_id=imported["skill"]["id"],
                version=published["version"],
            )
            bindings = store.list_app_skill_bindings(created_app["id"])
        finally:
            store.close()

        self.assertEqual(published["state"], "published")
        self.assertEqual(binding["permission_mode"], "require_confirmation")
        self.assertEqual(published_payload["skill_id"], "lesson_planner_skill")
        self.assertEqual(published_payload["version"], "2.0.0")
        self.assertEqual(published_payload["required_tools"], ["rag_retrieval_tool"])
        self.assertEqual(published_payload["required_permissions"], ["rag.read"])
        self.assertIn("workflow_definition", published_payload)
        self.assertEqual(
            bindings[0]["skill_version"],
            "2.0.0",
        )

    def test_published_skill_definition_falls_back_to_skill_md_when_db_metadata_is_stale(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = _make_execution_ready_skill_archive(self._tmpdir)

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            published = store.publish_skill_version(imported["version"]["id"])
            store.conn.execute(
                """
                UPDATE skill_versions
                SET metadata_json = ?
                WHERE id = ?
                """,
                (
                    json.dumps(
                        {
                            "description": "",
                            "required_tools": [],
                            "required_permissions": [],
                            "workflow_ref": "",
                            "input_schema_ref": "",
                            "output_schema_ref": "",
                        }
                    ),
                    published["id"],
                ),
            )
            store.conn.commit()
            published_payload = store.get_published_skill_definition(
                skill_id=imported["skill"]["id"],
                version=published["version"],
            )
        finally:
            store.close()

        self.assertEqual(published_payload["required_tools"], ["research_paper_search_tool"])
        self.assertEqual(published_payload["required_permissions"], ["external_api.read"])
        self.assertEqual(published_payload["input_schema"]["required"], ["topic"])
        self.assertEqual(
            published_payload["workflow_definition"]["steps"][0]["toolId"],
            "research_paper_search_tool",
        )

    def test_bind_route_uses_submitted_app_id(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = _make_skill_archive(self._tmpdir, version="3.0.0")
        app_one = {
            "name": "First App",
            "slug": "first-app",
            "description": "First app.",
            "starter_questions": ["one", "two", "three", "four"],
            "instructions": "# one",
            "version": "v1",
        }
        app_two = {
            "name": "Second App",
            "slug": "second-app",
            "description": "Second app.",
            "starter_questions": ["one", "two", "three", "four"],
            "instructions": "# two",
            "version": "v1",
        }

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            created_one = store.create_application(app_one)
            created_two = store.create_application(app_two)
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            published = store.publish_skill_version(imported["version"]["id"])

            client = app_module.app.test_client()
            response = client.post(
                f"/skills/{imported['skill']['id']}/bind",
                data={
                    "app_id": created_two["id"],
                    "skill_version": published["version"],
                    "permission_mode": "auto_allow",
                },
            )

            bindings_two = store.list_app_skill_bindings(created_two["id"])
            bindings_one = store.list_app_skill_bindings(created_one["id"])
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(bindings_one), 0)
        self.assertEqual(len(bindings_two), 1)
        self.assertEqual(bindings_two[0]["app_id"], created_two["id"])

    def test_skill_detail_lists_newest_binding_first(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = _make_skill_archive(self._tmpdir, version="4.0.0")
        older_app = {
            "name": "Older App",
            "slug": "older-app",
            "description": "Older app.",
            "starter_questions": ["one", "two", "three", "four"],
            "instructions": "# older",
            "version": "v1",
        }
        newer_app = {
            "name": "Newer App",
            "slug": "newer-app",
            "description": "Newer app.",
            "starter_questions": ["one", "two", "three", "four"],
            "instructions": "# newer",
            "version": "v1",
        }

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            created_older = store.create_application(older_app)
            created_newer = store.create_application(newer_app)
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            published = store.publish_skill_version(imported["version"]["id"])
            store.create_app_skill_binding(
                app_id=created_older["id"],
                skill_id=imported["skill"]["id"],
                skill_version=published["version"],
                permission_mode="auto_allow",
            )
            store.create_app_skill_binding(
                app_id=created_newer["id"],
                skill_id=imported["skill"]["id"],
                skill_version=published["version"],
                permission_mode="auto_allow",
            )
            store.conn.execute(
                "UPDATE app_skill_bindings SET created_at = ?, updated_at = ?",
                ("2026-08-27T00:00:00", "2026-08-27T00:00:00"),
            )
            store.conn.commit()

            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        bindings_section = body.split(">Bindings</h2>", 1)[1]
        self.assertLess(
            bindings_section.index("Newer App"),
            bindings_section.index("Older App"),
        )

    def test_skill_test_page_prefills_research_topic_from_published_skill_schema(self) -> None:
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        archive_path = _make_execution_ready_skill_archive(self._tmpdir)

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            store.publish_skill_version(imported["version"]["id"])

            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}/test")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("DeepSeek Mixture of Exports Technology", body)
        self.assertIn("&#34;limit&#34;: 5", body)
        self.assertIn("&#34;source&#34;: &#34;auto&#34;", body)

    def test_skill_import_page_previews_contract_without_persisting_skill(self) -> None:
        src = self._tmpdir / "notebooklm_video_import_preview_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: notebooklm-video-generator",
                    "version: 1.0",
                    "tools:",
                    "  - adapter.notebooklm.generate_video",
                    "permissions:",
                    "  - external_api.write",
                    "permission_class: review_required",
                    "---",
                    "",
                    "Input Schema",
                    "------------",
                    "",
                    "```json",
                    "{",
                    '  "type": "object",',
                    '  "properties": {',
                    '    "notebookId": { "type": "string" },',
                    '    "notebookTitle": { "type": "string" },',
                    '    "instructions": { "type": "string" },',
                    '    "language": { "type": "string", "default": "en" }',
                    "  },",
                    '  "required": ["instructions"],',
                    '  "anyOf": [',
                    '    { "required": ["notebookId"] },',
                    '    { "required": ["notebookTitle"] }',
                    "  ]",
                    "}",
                    "```",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "notebooklm_video_import_preview.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            client = app_module.app.test_client()
            response = client.post(
                "/skills/import",
                data={
                    "scope": "managed",
                    "action": "preview",
                    "archive": (io.BytesIO(archive_path.read_bytes()), archive_path.name),
                },
                content_type="multipart/form-data",
            )
            body = response.get_data(as_text=True)
            skills = store.list_skills()
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Import Preview", body)
        self.assertIn("Contract source: explicit skill markdown sections", body)
        self.assertIn("high confidence first-class family", body)
        self.assertIn("Builder prefers notebookTitle over notebookId", body)
        self.assertIn("adapter.notebooklm.generate_video", body)
        self.assertEqual(skills, [])

    def test_skills_list_page_shows_contract_confidence_summary(self) -> None:
        src = self._tmpdir / "notebooklm_video_list_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: notebooklm-video-generator",
                    "version: 1.0",
                    "tools:",
                    "  - adapter.notebooklm.generate_video",
                    "permissions:",
                    "  - external_api.write",
                    "permission_class: review_required",
                    "---",
                    "",
                    "Input Schema",
                    "------------",
                    "",
                    "```json",
                    "{",
                    '  "type": "object",',
                    '  "properties": {',
                    '    "notebookId": { "type": "string" },',
                    '    "notebookTitle": { "type": "string" },',
                    '    "instructions": { "type": "string" }',
                    "  },",
                    '  "required": ["instructions"],',
                    '  "anyOf": [',
                    '    { "required": ["notebookId"] },',
                    '    { "required": ["notebookTitle"] }',
                    "  ]",
                    "}",
                    "```",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "notebooklm_video_list.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()
            response = client.get("/skills")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn(imported["skill"]["name"], body)
        self.assertIn("Version: 1.0", body)
        self.assertIn("Template: notebooklm_generate_video_operation", body)
        self.assertIn("Contract source: explicit skill markdown sections", body)
        self.assertIn("high confidence first-class family", body)

    def test_skills_list_page_filters_by_normalization_confidence(self) -> None:
        notebook_src = self._tmpdir / "notebooklm_video_list_filter_src"
        notebook_src.mkdir(parents=True, exist_ok=True)
        (notebook_src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: notebooklm-video-generator",
                    "version: 1.0",
                    "tools:",
                    "  - adapter.notebooklm.generate_video",
                    "permissions:",
                    "  - external_api.write",
                    "permission_class: review_required",
                    "---",
                    "",
                    "Input Schema",
                    "------------",
                    "",
                    "```json",
                    "{",
                    '  "type": "object",',
                    '  "properties": {',
                    '    "notebookTitle": { "type": "string" },',
                    '    "instructions": { "type": "string" }',
                    "  },",
                    '  "required": ["instructions"],',
                    '  "anyOf": [',
                    '    { "required": ["notebookTitle"] }',
                    "  ]",
                    "}",
                    "```",
                ]
            ),
            encoding="utf-8",
        )
        notebook_archive = self._tmpdir / "notebooklm_video_list_filter.zip"
        with zipfile.ZipFile(notebook_archive, "w") as archive:
            archive.write(notebook_src / "SKILL.md", "SKILL.md")

        unsupported_archive = _make_descriptive_skill_archive(
            self._tmpdir,
            folder_name="unsupported_filter_skill_src",
            archive_name="unsupported_filter_skill.zip",
            skill_name="custom-unsupported-skill",
            description="Do a custom unsupported thing.",
            body_lines=[
                "## Workflow",
                "1. Call something Builder does not normalize.",
            ],
        )

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            notebook_import = store.import_skill_package(
                archive_path=notebook_archive,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            unsupported_import = store.import_skill_package(
                archive_path=unsupported_archive,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()
            response = client.get("/skills?confidence=high+confidence+first-class+family")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn(notebook_import["skill"]["name"], body)
        self.assertNotIn(unsupported_import["skill"]["name"], body)
        self.assertIn("value=\"high confidence first-class family\"", body)

    def test_skill_test_page_shows_inferred_contract_and_generated_input_notes(self) -> None:
        src = self._tmpdir / "notebooklm_video_skill_test_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: notebooklm-video-generator",
                    "version: 1.0",
                    "tools:",
                    "  - adapter.notebooklm.generate_video",
                    "permissions:",
                    "  - external_api.write",
                    "permission_class: review_required",
                    "---",
                    "",
                    "Input Schema",
                    "------------",
                    "",
                    "```json",
                    "{",
                    '  "type": "object",',
                    '  "properties": {',
                    '    "notebookId": { "type": "string" },',
                    '    "notebookTitle": { "type": "string" },',
                    '    "instructions": { "type": "string" },',
                    '    "language": { "type": "string", "default": "en" },',
                    '    "waitForCompletion": { "type": "boolean", "default": true },',
                    '    "persistArtifacts": { "type": "boolean", "default": true }',
                    "  },",
                    '  "required": ["instructions"],',
                    '  "anyOf": [',
                    '    { "required": ["notebookId"] },',
                    '    { "required": ["notebookTitle"] }',
                    "  ]",
                    "}",
                    "```",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "notebooklm_video_skill_test.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            store.publish_skill_version(imported["version"]["id"])

            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}/test")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Inferred Contract", body)
        self.assertIn("Generated Input Notes", body)
        self.assertIn("notebooklm_generate_video_operation", body)
        self.assertIn("explicit skill markdown sections", body)
        self.assertIn("high confidence first-class family", body)
        self.assertIn("Builder prefers notebookTitle over notebookId", body)
        self.assertIn("Included because the normalized input schema marks it as required.", body)
        self.assertIn("Included with its schema default", body)

    def test_skill_detail_page_shows_safe_read_review_panel(self) -> None:
        archive_path = _make_descriptive_skill_archive(
            self._tmpdir,
            folder_name="safe_review_skill_src",
            archive_name="safe_review_skill.zip",
            skill_name="file-inventory",
            description="Inspect a workspace path and save a summary report.",
            body_lines=[
                "# File Inventory",
                "",
                "## Inputs",
                "- path",
                "",
                "## Workflow",
                "1. List files under the target path.",
                "2. Save a report artifact.",
            ],
        )
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Safe Read", body)
        self.assertIn("list_files", body)
        self.assertIn("artifact.write", body)

    def test_skill_detail_page_shows_review_required_panel(self) -> None:
        archive_path = _make_descriptive_skill_archive(
            self._tmpdir,
            folder_name="risky_review_skill_src",
            archive_name="risky_review_skill.zip",
            skill_name="gmail-send-message",
            description="Send an email in Gmail.",
            body_lines=[
                "## Inputs",
                "- to",
                "- subject",
                "- body",
                "",
                "## Workflow",
                "1. Send the Gmail message.",
            ],
        )
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Review Required", body)
        self.assertIn("mcp.gmail.send_message", body)
        self.assertIn("external_api.write", body)
        self.assertIn("send_message", body)

    def test_skill_detail_page_shows_contract_source_explanation(self) -> None:
        src = self._tmpdir / "notebooklm_video_detail_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: notebooklm-video-generator",
                    "version: 1.0",
                    "tools:",
                    "  - adapter.notebooklm.generate_video",
                    "permissions:",
                    "  - external_api.write",
                    "permission_class: review_required",
                    "---",
                    "",
                    "Input Schema",
                    "------------",
                    "",
                    "```json",
                    "{",
                    '  "type": "object",',
                    '  "properties": {',
                    '    "notebookId": { "type": "string" },',
                    '    "notebookTitle": { "type": "string" },',
                    '    "instructions": { "type": "string" }',
                    "  },",
                    '  "required": ["instructions"],',
                    '  "anyOf": [',
                    '    { "required": ["notebookId"] },',
                    '    { "required": ["notebookTitle"] }',
                    "  ]",
                    "}",
                    "```",
                    "",
                    "Expected Output",
                    "---------------",
                    "",
                    "```json",
                    "{",
                    '  "type": "object",',
                    '  "properties": {',
                    '    "task_id": { "type": "string" },',
                    '    "status": { "type": "string" }',
                    "  },",
                    '  "required": ["task_id", "status"]',
                    "}",
                    "```",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "notebooklm_video_detail.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Contract Source", body)
        self.assertIn("Normalization Confidence", body)
        self.assertIn("Contract Explanation", body)
        self.assertIn("explicit skill markdown sections", body)
        self.assertIn("Builder used explicit structured sections from SKILL.md", body)
        self.assertIn("high confidence first-class family", body)
        self.assertIn("Template family: notebooklm_generate_video_operation.", body)

    def test_skill_detail_page_shows_fallback_capable_policy_details(self) -> None:
        src = self._tmpdir / "drive_gmail_review_skill_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: gmail-drive-attachment-sender-fileID",
                    "description: Download a Google Drive file and create a Gmail draft with it attached.",
                    "required_tools:",
                    "  - drive.download_file",
                    "  - gmail.create_draft_with_attachments",
                    "---",
                    "",
                    "## Inputs",
                    "- fileId",
                    "- to",
                    "- subject",
                    "- body",
                    "",
                    "## Workflow",
                    "1. Download the Google Drive file.",
                    "2. Save the result as an artifact.",
                    "3. Create a Gmail draft with the artifact attached.",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "drive_gmail_review_skill.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Fallback-capable tools", body)
        self.assertIn("mcp.gdrive.download_file_content", body)
        self.assertIn("mcp.gmail.create_draft_with_attachments", body)
        self.assertIn("artifact-only attachments", body)

    def test_skill_detail_page_shows_unsupported_review_panel(self) -> None:
        archive_path = _make_descriptive_skill_archive(
            self._tmpdir,
            folder_name="unsupported_review_skill_src",
            archive_name="unsupported_review_skill.zip",
            skill_name="creative-helper",
            description="Help think about creative ideas.",
            body_lines=[
                "Write creative suggestions for the user.",
            ],
        )
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()
            response = client.get(f"/skills/{imported['skill']['id']}")
            body = response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Unsupported", body)
        self.assertIn("No normalized executable contract available.", body)

    def test_delete_skill_removes_database_rows_and_storage_record(self) -> None:
        storage_root = self._tmpdir / "builder_storage"
        store = DatabaseStore(
            ":memory:",
            storage_root=storage_root,
            seed_data=False,
        )
        archive_path = _make_skill_archive(self._tmpdir)

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=storage_root / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            version = imported["version"]
            stored_root = store.base_dir / version["storage_root_rel_path"]
            self.assertTrue(stored_root.exists())

            deleted = store.delete_skill(imported["skill"]["id"])

            self.assertTrue(deleted)
            self.assertIsNone(store.get_skill(imported["skill"]["id"]))
            self.assertEqual(store.list_skill_versions(imported["skill"]["id"]), [])
            self.assertFalse(store.delete_skill(imported["skill"]["id"]))
        finally:
            store.close()

    def test_skill_detail_page_supports_deleting_a_skill(self) -> None:
        archive_path = _make_skill_archive(self._tmpdir)
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )

        app_module = importlib.import_module("app")
        original_store = app_module.store
        app_module.store = store
        app_module.app.config["TESTING"] = True

        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            client = app_module.app.test_client()

            detail_response = client.get(f"/skills/{imported['skill']['id']}")
            detail_body = detail_response.get_data(as_text=True)

            delete_response = client.post(
                f"/skills/{imported['skill']['id']}/delete",
                follow_redirects=True,
            )
            delete_body = delete_response.get_data(as_text=True)
        finally:
            app_module.store = original_store
            store.close()

        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("Delete Skill", detail_body)
        self.assertEqual(delete_response.status_code, 200)
        self.assertNotIn(imported["skill"]["name"], delete_body)

    def test_subsystem_page_shows_runtime_integration_inventory(self) -> None:
        class FakeExecutionClient:
            base_url = "http://127.0.0.1:3001"

            def get_runtime_readyz(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {
                        "checks": {
                            "runtime_config": {
                                "mcp": {
                                    "configuredServers": 2,
                                    "enabledServers": 2,
                                    "startupDiscoveryEnabled": True,
                                }
                            },
                            "mcp_discovery": {
                                "startupCompleted": True,
                                "providers": {
                                    "gmail": {
                                        "status": "success",
                                        "toolCount": 5,
                                        "toolIds": [
                                            "mcp.gmail.search_messages",
                                            "mcp.gmail.create_draft",
                                        ],
                                        "authConfigured": True,
                                    },
                                    "gdrive": {
                                        "status": "success",
                                        "toolCount": 2,
                                        "toolIds": [
                                            "mcp.gdrive.search_files",
                                            "mcp.gdrive.download_file_content",
                                        ],
                                        "authConfigured": True,
                                    },
                                },
                            },
                        }
                    },
                }

            def get_mcp_provider_status(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {
                        "startup_completed": True,
                        "providers": {
                            "gmail": {
                                "status": "success",
                                "tool_ids": [
                                    "mcp.gmail.search_messages",
                                    "mcp.gmail.create_draft",
                                ],
                            },
                            "gdrive": {
                                "status": "success",
                                "tool_ids": [
                                    "mcp.gdrive.search_files",
                                    "mcp.gdrive.download_file_content",
                                ],
                            },
                        },
                    },
                }

            def get_runtime_integrations(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {
                        "summary": {
                            "total_integrations": 5,
                            "by_family": {
                                "mcp": 2,
                                "adapter": 1,
                                "api": 1,
                                "local": 1,
                            },
                        },
                        "items": [
                            {
                                "id": "gmail",
                                "family": "mcp",
                                "configured": True,
                                "enabled": True,
                                "auth_configured": True,
                                "tool_count": 2,
                                "tool_ids": [
                                    "mcp.gmail.search_messages",
                                    "mcp.gmail.create_draft",
                                ],
                                "allowlisted_tools": [
                                    "search_messages",
                                    "create_draft",
                                ],
                                "health": {"status": "success", "last_error": None},
                            },
                            {
                                "id": "gdrive",
                                "family": "mcp",
                                "configured": True,
                                "enabled": True,
                                "auth_configured": True,
                                "tool_count": 2,
                                "tool_ids": [
                                    "mcp.gdrive.search_files",
                                    "mcp.gdrive.download_file_content",
                                ],
                                "allowlisted_tools": [
                                    "search_files",
                                    "download_file_content",
                                ],
                                "health": {"status": "success", "last_error": None},
                            },
                            {
                                "id": "notebooklm",
                                "family": "adapter",
                                "configured": True,
                                "enabled": True,
                                "auth_configured": True,
                                "tool_count": 2,
                                "tool_ids": [
                                    "adapter.notebooklm.ask",
                                    "adapter.notebooklm.generate_video",
                                ],
                                "allowed_operations": [
                                    "ask",
                                    "generate_video",
                                ],
                                "health": {"status": "configured", "last_error": None},
                            },
                        ],
                    },
                }

            def get_tool_inventory(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {
                        "items": [
                            {
                                "tool_id": "mcp.gdrive.download_file_content",
                                "family": "mcp",
                                "provider_id": "gdrive",
                                "enabled": True,
                                "permission_scopes": ["external_api.read"],
                                "side_effecting": False,
                                "timeout_ms": 15000,
                                "policy_class": "review_required",
                                "fallback_capable": True,
                                "fallback_strategy": "rest_api",
                            },
                            {
                                "tool_id": "adapter.notebooklm.generate_video",
                                "family": "adapter",
                                "provider_id": "notebooklm",
                                "enabled": True,
                                "permission_scopes": ["external_api.write"],
                                "side_effecting": True,
                                "timeout_ms": 240000,
                                "policy_class": "review_required",
                                "fallback_capable": False,
                                "fallback_strategy": None,
                            },
                        ]
                    },
                }

            def get_recent_execution_diagnostics(self, limit: int = 10, used_fallback=None, execution_path=None):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {
                        "summary": {
                            "total_executions": 1,
                            "fallback_executions": 1,
                            "by_execution_path": {
                                "rest_fallback": 1,
                            },
                            "by_provider": {
                                "gdrive": 1,
                            },
                            "by_tool": {
                                "mcp.gdrive.download_file_content": 1,
                            },
                        },
                        "items": [
                            {
                                "execution_id": "execution_001",
                                "app_id": "app_001",
                                "skill_id": "google_drive_download_file",
                                "status": "completed",
                                "updated_at": "2026-06-02T12:00:00Z",
                                "logs_summary": "Skill completed in 3 steps with 2 tool calls. 1 fallback path(s) used.",
                                "execution_metadata": {
                                    "used_fallback": True,
                                    "fallback_count": 1,
                                    "execution_paths": ["rest_fallback", "local"],
                                    "provider_ids": ["gdrive"],
                                    "tool_ids": [
                                        "mcp.gdrive.download_file_content",
                                        "save_artifact",
                                    ],
                                },
                            }
                        ]
                    },
                }

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        app_module = importlib.import_module("app")
        original_store = app_module.store
        original_execution_client = app_module._execution_client
        app_module.store = store
        app_module._execution_client = lambda: FakeExecutionClient()
        app_module.app.config["TESTING"] = True

        try:
            client = app_module.app.test_client()
            response = client.get("/admin/subsystem")
            body = response.get_data(as_text=True)
        finally:
            app_module._execution_client = original_execution_client
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertIn("Runtime Integration Inventory", body)
        self.assertIn("Execution base URL", body)
        self.assertIn("http://127.0.0.1:3001", body)
        self.assertIn("Startup auto-discovery", body)
        self.assertIn("gmail", body)
        self.assertIn("gdrive", body)
        self.assertIn("notebooklm", body)
        self.assertIn("Skill Authoring Coverage", body)
        self.assertIn("Runtime Tool Inventory", body)
        self.assertIn("/readyz", body)
        self.assertIn("/v1/tools/inventory", body)
        self.assertIn("notebooklm.generate_video", body)
        self.assertIn("adapter.notebooklm.generate_video", body)
        self.assertIn("default family inference supported", body)
        self.assertIn("mcp.gdrive.download_file_content", body)
        self.assertIn("Recent Execution Diagnostics", body)
        self.assertIn("execution_001", body)
        self.assertIn("google_drive_download_file", body)
        self.assertIn("rest_fallback", body)
        self.assertIn("Fallback Summary", body)
        self.assertIn("Total executions", body)
        self.assertIn("mcp.gdrive.download_file_content", body)

    def test_execution_client_defaults_to_local_execution_subsystem_port(self) -> None:
        app_module = importlib.import_module("app")
        original_value = os.environ.pop("RAGENIUS_EXECUTION_BASE_URL", None)

        try:
            client = app_module._execution_client()
        finally:
            if original_value is not None:
                os.environ["RAGENIUS_EXECUTION_BASE_URL"] = original_value

        self.assertEqual(client.base_url, "http://127.0.0.1:3001")

    def test_subsystem_page_refreshes_mcp_provider_status(self) -> None:
        class FakeExecutionClient:
            def refresh_mcp_provider(self, provider_id: str):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {
                        "provider_id": provider_id,
                        "tools_discovered": [
                            {
                                "id": "mcp.gdrive.download_file_content",
                                "provider_type": "mcp",
                            }
                        ],
                    },
                }

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        app_module = importlib.import_module("app")
        original_store = app_module.store
        original_execution_client = app_module._execution_client
        app_module.store = store
        app_module._execution_client = lambda: FakeExecutionClient()
        app_module.app.config["TESTING"] = True

        try:
            client = app_module.app.test_client()
            response = client.post("/admin/subsystem/mcp/providers/gdrive/refresh")
        finally:
            app_module._execution_client = original_execution_client
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["provider_id"], "gdrive")
        self.assertEqual(
            payload["tools_discovered"][0]["id"],
            "mcp.gdrive.download_file_content",
        )

    def test_subsystem_tools_info_export_writes_markdown_from_runtime_inventory(self) -> None:
        class FakeExecutionClient:
            def get_runtime_readyz(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {"checks": {"runtime_config": {"mcp": {}}, "mcp_discovery": {}}},
                }

            def get_mcp_provider_status(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {"startup_completed": True, "providers": {}},
                }

            def get_runtime_integrations(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {"items": [], "summary": {"total_integrations": 0, "by_family": {}}},
                }

            def get_tool_inventory(self):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {
                        "items": [
                            {
                                "tool_id": "retrieve_documents",
                                "name": "Retrieve Documents",
                                "family": "rag_adapter",
                                "provider_id": "rag_subsystem",
                                "enabled": True,
                                "permission_scopes": ["rag.read"],
                                "side_effecting": False,
                                "timeout_ms": 2000,
                                "policy_class": "safe_read",
                                "fallback_capable": False,
                                "fallback_strategy": None,
                                "input_schema": {
                                    "type": "object",
                                    "properties": {
                                        "query": {"type": "string"},
                                        "top_k": {"type": "number"},
                                    },
                                    "required": ["query"],
                                },
                                "output_schema": {
                                    "type": "object",
                                    "properties": {
                                        "items": {"type": "array"},
                                    },
                                    "required": ["items"],
                                },
                                "metadata": {
                                    "policyClass": "safe_read",
                                },
                            },
                            {
                                "tool_id": "adapter.notebooklm.generate_video",
                                "name": "NotebookLM Generate Video",
                                "family": "adapter",
                                "provider_id": "notebooklm",
                                "enabled": True,
                                "permission_scopes": ["external_api.write"],
                                "side_effecting": True,
                                "timeout_ms": 240000,
                                "policy_class": "review_required",
                                "fallback_capable": False,
                                "fallback_strategy": None,
                                "input_schema": {
                                    "type": "object",
                                    "properties": {
                                        "notebookId": {"type": "string"},
                                        "instructions": {"type": "string"},
                                    },
                                    "required": ["instructions"],
                                },
                                "output_schema": {
                                    "type": "object",
                                    "properties": {
                                        "artifact_id": {"type": "string"},
                                    },
                                    "required": ["artifact_id"],
                                },
                                "metadata": {
                                    "requiresConfirmation": True,
                                },
                            },
                        ]
                    },
                }

            def get_recent_execution_diagnostics(self, limit: int = 10, used_fallback=None, execution_path=None):
                return {
                    "ok": True,
                    "status_code": 200,
                    "body": {"items": [], "summary": {}},
                }

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        app_module = importlib.import_module("app")
        original_store = app_module.store
        original_execution_client = app_module._execution_client
        original_export_path = app_module._TOOLS_INFO_EXPORT_PATH
        export_path = self._tmpdir / "docs" / "tools_info.md"
        app_module.store = store
        app_module._execution_client = lambda: FakeExecutionClient()
        app_module._TOOLS_INFO_EXPORT_PATH = export_path
        app_module.app.config["TESTING"] = True

        try:
            client = app_module.app.test_client()
            response = client.post(
                "/admin/subsystem/tools-info/export",
                follow_redirects=True,
            )
            body = response.get_data(as_text=True)
        finally:
            app_module._TOOLS_INFO_EXPORT_PATH = original_export_path
            app_module._execution_client = original_execution_client
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(export_path.exists())
        exported = export_path.read_text(encoding="utf-8")
        self.assertIn("tools_info.md export written", body)
        self.assertIn("docs/tools_info.md", body)
        self.assertIn("# RAGenius Tools Inventory", exported)
        self.assertIn("## `retrieve_documents`", exported)
        self.assertIn("## `adapter.notebooklm.generate_video`", exported)
        self.assertIn("Permission scopes: `rag.read`", exported)
        self.assertIn("Permission scopes: `external_api.write`", exported)
        self.assertIn("Side effects: `read_only`", exported)
        self.assertIn("Side effects: `write`", exported)
        self.assertIn('"query": {', exported)
        self.assertIn('"instructions": {', exported)
        self.assertIn('"artifact_id": {', exported)

    def test_subsystem_tools_info_export_writes_diagnostic_markdown_when_inventory_unavailable(self) -> None:
        class FakeExecutionClient:
            def get_runtime_readyz(self):
                return {
                    "ok": False,
                    "status_code": None,
                    "body": {"error": {"message": "connection refused"}},
                }

            def get_mcp_provider_status(self):
                return {"ok": False, "status_code": None, "body": {}}

            def get_runtime_integrations(self):
                return {"ok": False, "status_code": None, "body": {}}

            def get_tool_inventory(self):
                return {
                    "ok": False,
                    "status_code": None,
                    "body": {
                        "error": {
                            "code": "EXECUTION_SUBSYSTEM_UNAVAILABLE",
                            "message": "connection refused",
                        }
                    },
                }

            def get_recent_execution_diagnostics(self, limit: int = 10, used_fallback=None, execution_path=None):
                return {"ok": False, "status_code": None, "body": {}}

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        app_module = importlib.import_module("app")
        original_store = app_module.store
        original_execution_client = app_module._execution_client
        original_export_path = app_module._TOOLS_INFO_EXPORT_PATH
        export_path = self._tmpdir / "docs" / "tools_info.md"
        app_module.store = store
        app_module._execution_client = lambda: FakeExecutionClient()
        app_module._TOOLS_INFO_EXPORT_PATH = export_path
        app_module.app.config["TESTING"] = True

        try:
            client = app_module.app.test_client()
            response = client.post(
                "/admin/subsystem/tools-info/export",
                follow_redirects=True,
            )
            body = response.get_data(as_text=True)
        finally:
            app_module._TOOLS_INFO_EXPORT_PATH = original_export_path
            app_module._execution_client = original_execution_client
            app_module.store = original_store
            store.close()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(export_path.exists())
        exported = export_path.read_text(encoding="utf-8")
        self.assertIn("tools_info.md export written", body)
        self.assertIn("# RAGenius Tools Inventory Export Failed", exported)
        self.assertIn("EXECUTION_SUBSYSTEM_UNAVAILABLE", exported)
        self.assertIn("connection refused", exported)
        self.assertIn("RAGENIUS_EXECUTION_BASE_URL", exported)

    def test_normalize_safe_read_skill_builds_file_inspection_draft(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: file-inventory",
                "description: Inspect a workspace path and save a summary report.",
                "---",
                "",
                "# File Inventory",
                "",
                "## Inputs",
                "- path",
                "",
                "## Workflow",
                "1. List files under the target path.",
                "2. Save a report artifact.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "file_inspection_report")
        self.assertEqual(draft["policy_class"], "safe_read")
        self.assertEqual(draft["candidate_tools"], ["list_files", "save_artifact"])

    def test_normalize_safe_read_skill_generates_finalized_contract(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: retrieval-summary",
                "description: Retrieve relevant app documents and save a summary artifact.",
                "---",
                "",
                "## Inputs",
                "- query",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertTrue(draft["auto_finalize"])
        self.assertEqual(
            draft["required_tools"], ["retrieve_documents", "save_artifact"]
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["toolId"],
            "retrieve_documents",
        )
        self.assertEqual(draft["input_schema"]["required"], ["query"])

    def test_normalize_explicit_research_paper_tool_contract(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "id: topic_research_paper_finder",
                "name: topic-research-paper-finder",
                "version: 1.0.0",
                "description: Find and summarize top research papers for a user-defined topic using research_paper_search_tool.",
                "required_tools:",
                "  - research_paper_search_tool",
                "required_permissions:",
                "  - external_api.read",
                "---",
                "",
                "## Tool Contract",
                "Call `research_paper_search_tool` using topic, limit, and source.",
                "Expected response includes topic, source, and papers.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "research_paper_search_operation")
        self.assertEqual(draft["policy_class"], "safe_read")
        self.assertTrue(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["research_paper_search_tool"])
        self.assertEqual(draft["required_permissions"], ["external_api.read"])
        self.assertEqual(draft["input_schema"]["required"], ["topic"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["toolId"],
            "research_paper_search_tool",
        )
        self.assertEqual(
            draft["output_schema"]["required"],
            ["topic", "source", "papers"],
        )

    def test_normalize_author_facing_gmail_send_draft_alias(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-send-draft",
                "description: Send an existing Gmail draft.",
                "required_tools:",
                "  - gmail.send_draft",
                "---",
                "",
                "## Inputs",
                "- draftId",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_send_draft_operation")
        self.assertEqual(draft["required_tools"], ["mcp.gmail.send_draft"])
        self.assertEqual(draft["required_permissions"], ["external_api.write"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gmail.send_draft",
        )

    def test_normalize_author_facing_drive_download_alias(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: drive-download-file",
                "description: Download a Google Drive file and save it as an artifact.",
                "required_tools:",
                "  - drive.download_file",
                "---",
                "",
                "## Inputs",
                "- fileId",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "google_drive_export_operation")
        self.assertEqual(
            draft["required_tools"],
            ["mcp.gdrive.download_file_content", "save_artifact"],
        )
        self.assertEqual(
            draft["required_permissions"],
            ["external_api.read", "artifact.write"],
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gdrive.download_file_content",
        )

    def test_normalize_author_facing_drive_to_gmail_attachment_draft_aliases(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: drive-to-gmail-attachment-draft",
                "description: Download a Google Drive file and create a Gmail draft with it attached.",
                "required_tools:",
                "  - drive.download_file",
                "  - gmail.create_draft_with_attachments",
                "---",
                "",
                "## Inputs",
                "- fileId",
                "- to",
                "- subject",
                "- body",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(
            draft["template_family"],
            "google_drive_to_gmail_attachment_draft_operation",
        )
        self.assertEqual(
            draft["required_tools"],
            [
                "mcp.gdrive.download_file_content",
                "save_artifact",
                "mcp.gmail.create_draft_with_attachments",
            ],
        )
        self.assertEqual(
            draft["required_permissions"],
            [
                "external_api.read",
                "artifact.write",
                "artifact.read",
                "external_api.write",
            ],
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gdrive.download_file_content",
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][1]["toolId"],
            "save_artifact",
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][2]["serviceId"],
            "mcp.gmail.create_draft_with_attachments",
        )

    def test_import_skill_package_stores_normalized_contract_metadata(self) -> None:
        src = self._tmpdir / "safe_skill_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: file-inventory",
                    "description: Inspect a workspace path and save a summary report.",
                    "---",
                    "",
                    "# File Inventory",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "file_inventory.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            published = store.publish_skill_version(imported["version"]["id"])
            payload = store.get_published_skill_definition(
                skill_id=imported["skill"]["id"],
                version=published["version"],
            )
        finally:
            store.close()

        self.assertEqual(payload["required_tools"], ["list_files", "save_artifact"])
        self.assertEqual(payload["workflow_definition"]["steps"][0]["toolId"], "list_files")

    def test_import_markdown_only_research_paper_skill_builds_runtime_contract(self) -> None:
        archive_path = _make_research_paper_skill_markdown_only_archive(self._tmpdir)
        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            published = store.publish_skill_version(imported["version"]["id"])
            payload = store.get_published_skill_definition(
                skill_id=imported["skill"]["id"],
                version=published["version"],
            )
        finally:
            store.close()

        self.assertEqual(payload["required_tools"], ["research_paper_search_tool"])
        self.assertEqual(payload["required_permissions"], ["external_api.read"])
        self.assertEqual(payload["input_schema"]["required"], ["topic"])
        self.assertEqual(
            payload["workflow_definition"]["steps"][0]["toolId"],
            "research_paper_search_tool",
        )
        self.assertEqual(
            payload["output_schema"]["required"],
            ["topic", "source", "papers"],
        )

    def test_import_markdown_only_gmail_send_draft_alias_builds_runtime_contract(self) -> None:
        src = self._tmpdir / "gmail_send_draft_alias_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: gmail-send-draft",
                    "description: Send an existing Gmail draft.",
                    "required_tools:",
                    "  - gmail.send_draft",
                    "---",
                    "",
                    "## Inputs",
                    "- draftId",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "gmail_send_draft_alias.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            payload = store.get_skill_version(imported["version"]["id"])
        finally:
            store.close()

        metadata = payload["metadata"]
        self.assertEqual(metadata["template_family"], "gmail_send_draft_operation")
        self.assertEqual(metadata["required_tools"], ["mcp.gmail.send_draft"])
        self.assertEqual(metadata["required_permissions"], ["external_api.write"])

    def test_import_markdown_only_drive_to_gmail_attachment_draft_aliases_builds_runtime_contract(self) -> None:
        src = self._tmpdir / "drive_to_gmail_attachment_draft_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: drive-to-gmail-attachment-draft",
                    "description: Download a Google Drive file and create a Gmail draft with it attached.",
                    "required_tools:",
                    "  - drive.download_file",
                    "  - gmail.create_draft_with_attachments",
                    "---",
                    "",
                    "## Inputs",
                    "- fileId",
                    "- to",
                    "- subject",
                    "- body",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "drive_to_gmail_attachment_draft.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            payload = store.get_skill_version(imported["version"]["id"])
        finally:
            store.close()

        metadata = payload["metadata"]
        self.assertEqual(
            metadata["template_family"],
            "google_drive_to_gmail_attachment_draft_operation",
        )
        self.assertEqual(
            metadata["required_tools"],
            [
                "mcp.gdrive.download_file_content",
                "save_artifact",
                "mcp.gmail.create_draft_with_attachments",
            ],
        )
        self.assertEqual(
            metadata["workflow_definition"]["steps"][2]["serviceId"],
            "mcp.gmail.create_draft_with_attachments",
        )

    def test_normalize_mutation_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: patch-homepage-copy",
                "description: Update the homepage markdown copy and save the result.",
                "---",
                "",
                "## Inputs",
                "- path",
                "- patch",
                "",
                "## Workflow",
                "1. Read the existing file.",
                "2. Apply a patch to the file.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "content_patch")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(
            draft["required_tools"],
            ["read_file", "patch_file", "save_artifact"],
        )

    def test_import_skill_package_keeps_mutation_contract_in_review_state(
        self,
    ) -> None:
        src = self._tmpdir / "mutation_skill_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: patch-homepage-copy",
                    "description: Apply a patch to an existing markdown file.",
                    "---",
                    "",
                    "1. Read the file.",
                    "2. Apply a patch to the file.",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "patch_homepage_copy.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        try:
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            version = store.get_skill_version(imported["version"]["id"])
        finally:
            store.close()

        self.assertEqual(imported["version"]["state"], "review")
        self.assertIsNotNone(version)
        self.assertEqual(version["metadata"]["policy_class"], "review_required")
        self.assertEqual(
            version["metadata"]["workflow_definition"]["steps"][1]["toolId"],
            "patch_file",
        )

    def test_normalize_mcp_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: publish-page",
                "description: Use the site CMS MCP provider to create a page.",
                "---",
                "",
                "## Inputs",
                "- title",
                "",
                "## Workflow",
                "1. Create a page in the CMS MCP provider.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "mcp_write_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])

    def test_normalize_gmail_read_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-message-search",
                "description: Search Gmail messages through the Gmail MCP provider.",
                "---",
                "",
                "## Inputs",
                "- query",
                "",
                "## Workflow",
                "1. Search Gmail messages.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_read_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gmail.search_messages"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gmail.search_messages",
        )

    def test_normalize_google_docs_read_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: google-docs-search",
                "description: Search Google Docs documents through the Google Docs MCP provider.",
                "---",
                "",
                "## Inputs",
                "- query",
                "",
                "## Workflow",
                "1. Search Google Docs documents.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "google_docs_read_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gdocs.search_documents"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gdocs.search_documents",
        )

    def test_normalize_google_drive_read_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: google-drive-search",
                "description: Search Google Drive files through the Google Drive MCP provider.",
                "---",
                "",
                "## Inputs",
                "- query",
                "",
                "## Workflow",
                "1. Search Google Drive files.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "google_drive_read_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gdrive.search_files"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gdrive.search_files",
        )

    def test_normalize_google_drive_export_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: google-drive-download",
                "description: Download a Google Drive file through the Google Drive MCP provider.",
                "---",
                "",
                "## Inputs",
                "- fileId",
                "",
                "## Workflow",
                "1. Download the Google Drive file.",
                "2. Save the result as an artifact.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "google_drive_export_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(
            draft["required_tools"],
            ["mcp.gdrive.download_file_content", "save_artifact"],
        )
        self.assertEqual(
            draft["required_permissions"],
            ["external_api.read", "artifact.write"],
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gdrive.download_file_content",
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][1]["toolId"],
            "save_artifact",
        )

    def test_normalize_gmail_draft_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-create-draft",
                "description: Create a draft email in Gmail.",
                "---",
                "",
                "## Inputs",
                "- to",
                "- subject",
                "- body",
                "",
                "## Workflow",
                "1. Create a Gmail draft.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_draft_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gmail.create_draft"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gmail.create_draft",
        )
        self.assertEqual(draft["input_schema"]["required"], ["to", "subject", "body"])

    def test_normalize_gmail_attachment_draft_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-draft-with-attachments",
                "description: Create a Gmail draft with attachments from artifacts.",
                "---",
                "",
                "## Inputs",
                "- to",
                "- subject",
                "- body",
                "- artifactIds",
                "",
                "## Workflow",
                "1. Create a Gmail draft.",
                "2. Attach the artifacts.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_attachment_draft_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(
            draft["required_tools"],
            ["mcp.gmail.create_draft_with_attachments"],
        )
        self.assertEqual(
            draft["required_permissions"],
            ["external_api.write", "artifact.read"],
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gmail.create_draft_with_attachments",
        )
        self.assertEqual(
            draft["input_schema"]["required"],
            ["to", "subject", "body", "artifactIds"],
        )

    def test_normalize_gmail_send_draft_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-send-draft",
                "description: Send an existing Gmail draft.",
                "---",
                "",
                "## Inputs",
                "- draftId",
                "",
                "## Workflow",
                "1. Send the Gmail draft.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_send_draft_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gmail.send_draft"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gmail.send_draft",
        )
        self.assertEqual(draft["input_schema"]["required"], ["draftId"])

    def test_normalize_gmail_send_message_skill_marks_review_required(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: gmail-send-message",
                "description: Send an email in Gmail.",
                "---",
                "",
                "## Inputs",
                "- to",
                "- subject",
                "- body",
                "",
                "## Workflow",
                "1. Send the Gmail message.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "gmail_send_message_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["mcp.gmail.send_message"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "mcp.gmail.send_message",
        )
        self.assertEqual(draft["input_schema"]["required"], ["to", "subject", "body"])

    def test_normalize_author_facing_notebooklm_ask_alias(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: notebooklm-ask",
                "description: Ask a question against an existing NotebookLM notebook.",
                "required_tools:",
                "  - notebooklm.ask",
                "required_permissions:",
                "  - external_api.read",
                "---",
                "",
                "## Inputs",
                "- notebookId",
                "- question",
                "",
                "## Workflow",
                "1. Ask NotebookLM about the notebook.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(draft["template_family"], "notebooklm_ask_operation")
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(draft["required_tools"], ["adapter.notebooklm.ask"])
        self.assertEqual(
            draft["required_permissions"],
            ["external_api.read"],
        )
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "adapter.notebooklm.ask",
        )
        self.assertEqual(draft["input_schema"]["required"], ["question"])
        self.assertIn("anyOf", draft["input_schema"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["inputMapping"]["notebookTitle"],
            "$.input.notebookTitle",
        )

    def test_normalize_author_facing_notebooklm_add_source_text_alias(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: notebooklm-add-source-text",
                "description: Add text content to an existing NotebookLM notebook.",
                "required_tools:",
                "  - notebooklm.add_source_text",
                "required_permissions:",
                "  - external_api.write",
                "---",
                "",
                "## Inputs",
                "- notebookId",
                "- title",
                "- content",
                "",
                "## Workflow",
                "1. Add the text source to the notebook.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(
            draft["template_family"], "notebooklm_add_source_text_operation"
        )
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(
            draft["required_tools"], ["adapter.notebooklm.add_source_text"]
        )
        self.assertEqual(draft["required_permissions"], ["external_api.write"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "adapter.notebooklm.add_source_text",
        )
        self.assertEqual(
            draft["input_schema"]["required"], ["title", "content"]
        )
        self.assertIn("anyOf", draft["input_schema"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["inputMapping"]["notebookTitle"],
            "$.input.notebookTitle",
        )

    def test_normalize_author_facing_notebooklm_generate_slide_deck_alias(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: notebooklm-generate-slide-deck",
                "description: Generate a slide deck from an existing NotebookLM notebook.",
                "required_tools:",
                "  - notebooklm.generate_slide_deck",
                "required_permissions:",
                "  - external_api.write",
                "---",
                "",
                "## Inputs",
                "- notebookId",
                "",
                "## Workflow",
                "1. Generate the slide deck.",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(
            draft["template_family"], "notebooklm_generate_slide_deck_operation"
        )
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertFalse(draft["auto_finalize"])
        self.assertEqual(
            draft["required_tools"], ["adapter.notebooklm.generate_slide_deck"]
        )
        self.assertEqual(draft["required_permissions"], ["external_api.write"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["serviceId"],
            "adapter.notebooklm.generate_slide_deck",
        )
        self.assertEqual(draft["input_schema"]["required"], [])
        self.assertIn("anyOf", draft["input_schema"])
        self.assertEqual(
            draft["workflow_definition"]["steps"][0]["inputMapping"]["notebookTitle"],
            "$.input.notebookTitle",
        )

    def test_parse_skill_manifest_supports_richer_yaml_frontmatter(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: notebooklm-video-generator",
                "description: Use NotebookLM tools to create a video from a selected notebook project.",
                "version: 1.0",
                "author: openclaw",
                "capabilities:",
                "  - name: generate_notebooklm_video",
                "    description: Create a NotebookLM video from a selected notebook using the provided video instructions.",
                "tools:",
                "  - adapter.notebooklm.generate_video",
                "permissions:",
                "  - external_api.write",
                "permission_class: review_required",
                "execution:",
                "  timeout: 300",
                "metadata:",
                "  pattern:",
                "    - tool-wrapper",
                "    - pipeline",
                "  author_alias: notebooklm.generate_video",
                "  domain: notebooklm",
                "---",
                "",
                "Body",
            ]
        )

        manifest = DatabaseStore._normalize_skill_manifest(
            DatabaseStore._parse_skill_manifest(markdown)
        )

        self.assertEqual(manifest["name"], "notebooklm-video-generator")
        self.assertEqual(manifest["version"], "1.0")
        self.assertEqual(
            manifest["required_tools"], ["adapter.notebooklm.generate_video"]
        )
        self.assertEqual(manifest["required_permissions"], ["external_api.write"])
        self.assertEqual(manifest["permission_class"], "review_required")
        self.assertEqual(manifest["execution"]["timeout"], 300)
        self.assertEqual(
            manifest["metadata"]["author_alias"], "notebooklm.generate_video"
        )

    def test_normalize_rich_notebooklm_video_formatter_uses_explicit_sections(self) -> None:
        markdown = "\n".join(
            [
                "---",
                "name: notebooklm-video-generator",
                "description: Use NotebookLM tools to create a video from a selected notebook project.",
                "version: 1.0",
                "tools:",
                "  - adapter.notebooklm.generate_video",
                "permissions:",
                "  - external_api.write",
                "permission_class: review_required",
                "metadata:",
                "  author_alias: notebooklm.generate_video",
                "---",
                "",
                "Input Schema",
                "------------",
                "",
                "```json",
                "{",
                '  "type": "object",',
                '  "properties": {',
                '    "notebookId": { "type": "string" },',
                '    "notebookTitle": { "type": "string" },',
                '    "instructions": { "type": "string" },',
                '    "waitForCompletion": { "type": "boolean", "default": true }',
                "  },",
                '  "required": ["instructions"],',
                '  "anyOf": [',
                '    { "required": ["notebookId"] },',
                '    { "required": ["notebookTitle"] }',
                "  ]",
                "}",
                "```",
                "",
                "Workflow",
                "--------",
                "",
                "1. Validate that instructions is present.",
                "2. Validate that either notebookTitle or notebookId is present.",
                "3. Call adapter.notebooklm.generate_video.",
                "",
                "Expected Output",
                "---------------",
                "",
                "```json",
                "{",
                '  "type": "object",',
                '  "properties": {',
                '    "notebook_id": { "type": "string" },',
                '    "artifact_kind": { "type": "string" },',
                '    "task_id": { "type": "string" },',
                '    "status": { "type": "string" }',
                "  },",
                '  "required": ["notebook_id", "artifact_kind", "task_id", "status"]',
                "}",
                "```",
            ]
        )

        from skill_normalization import normalize_skill_markdown

        draft = normalize_skill_markdown(markdown)

        self.assertEqual(
            draft["template_family"], "notebooklm_generate_video_operation"
        )
        self.assertEqual(draft["policy_class"], "review_required")
        self.assertEqual(
            draft["required_tools"], ["adapter.notebooklm.generate_video"]
        )
        self.assertEqual(draft["required_permissions"], ["external_api.write"])
        self.assertEqual(
            draft["input_schema"]["required"], ["instructions"]
        )
        self.assertIn("anyOf", draft["input_schema"])
        self.assertEqual(
            draft["output_schema"]["required"],
            ["notebook_id", "artifact_kind", "task_id", "status"],
        )

    def test_default_skill_test_input_prefers_notebook_title_for_conditional_schema(self):
        src = self._tmpdir / "notebooklm_video_skill_src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "SKILL.md").write_text(
            "\n".join(
                [
                    "---",
                    "name: notebooklm-video-generator",
                    "version: 1.0",
                    "tools:",
                    "  - adapter.notebooklm.generate_video",
                    "permissions:",
                    "  - external_api.write",
                    "permission_class: review_required",
                    "---",
                    "",
                    "Input Schema",
                    "------------",
                    "",
                    "```json",
                    "{",
                    '  "type": "object",',
                    '  "properties": {',
                    '    "notebookId": { "type": "string" },',
                    '    "notebookTitle": { "type": "string" },',
                    '    "instructions": { "type": "string" },',
                    '    "language": { "type": "string", "default": "en" },',
                    '    "waitForCompletion": { "type": "boolean", "default": true },',
                    '    "persistArtifacts": { "type": "boolean", "default": true }',
                    "  },",
                    '  "required": ["instructions"],',
                    '  "anyOf": [',
                    '    { "required": ["notebookId"] },',
                    '    { "required": ["notebookTitle"] }',
                    "  ]",
                    "}",
                    "```",
                ]
            ),
            encoding="utf-8",
        )
        archive_path = self._tmpdir / "notebooklm_video_skill.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.write(src / "SKILL.md", "SKILL.md")

        import app as builder_app

        store = DatabaseStore(
            ":memory:",
            storage_root=self._tmpdir / "builder_storage",
            seed_data=False,
        )
        original_store = builder_app.store
        try:
            builder_app.store = store
            imported = store.import_skill_package(
                archive_path=archive_path,
                storage_root=self._tmpdir / "managed_skills",
                scope="managed",
                import_source="upload",
            )
            store.publish_skill_version(imported["version"]["id"])
            payload = json.loads(builder_app._default_skill_test_input(imported["skill"]["id"]))
        finally:
            builder_app.store = original_store
            store.close()

        self.assertEqual(payload["instructions"], "example")
        self.assertEqual(payload["notebookTitle"], "example")
        self.assertNotIn("notebookId", payload)
        self.assertEqual(payload["language"], "en")
        self.assertTrue(payload["waitForCompletion"])
        self.assertTrue(payload["persistArtifacts"])


if __name__ == "__main__":
    unittest.main()
