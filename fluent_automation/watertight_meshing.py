from pathlib import Path
from typing import Any, cast

import ansys.fluent.core as pyfluent
from ansys.fluent.core import examples

from fluent_automation.config import (
    BoundaryLayerSetting,
    BoundaryTypeSetting,
    CapSetting,
    GuiPauseConfig,
    WatertightMeshConfig,
)
from fluent_automation.console import pause_for_gui, print_color
from fluent_automation.pyfluent_helpers import fluent_yes_no, get_workflow_task
from fluent_automation.protocols import MeshingSession


class WatertightMesher:
    """Watertight Geometry workflowで表面メッシュ・体積メッシュを作成する。"""

    def __init__(
        self,
        config: WatertightMeshConfig,
        pause_config: GuiPauseConfig | None = None,
    ):
        self.config = config
        self.pause_config = pause_config or GuiPauseConfig()
        self.meshing_session: MeshingSession | None = None
        self.watertight: Any = None

    def create(self) -> MeshingSession:
        """メッシュ作成workflowを実行し、meshing sessionを返す。"""

        geometry_file = self._resolve_geometry_file()
        self._launch_meshing_session()
        self._import_geometry(geometry_file)
        self._generate_surface_mesh()
        self._describe_geometry()

        if self.config.capping_required:
            self._create_caps()
            self._create_regions()

        self._update_boundaries()
        self._update_regions()
        self._create_boundary_layers()
        self._generate_volume_mesh()
        return self._require_meshing_session()

    def _require_meshing_session(self) -> MeshingSession:
        if self.meshing_session is None:
            raise RuntimeError("Fluent meshing session has not been launched.")

        return self.meshing_session

    def _resolve_geometry_file(self) -> str:
        if self.config.geometry_file is None:
            geometry_file = examples.download_file(
                "mixing_elbow.pmdb",
                "pyfluent/mixing_elbow",
            )
        else:
            geometry_file = self.config.geometry_file

        return str(Path(geometry_file).resolve())

    def _launch_meshing_session(self) -> None:
        """FluentをMeshingモードで起動し、Watertight workflowを開始する。"""

        print_color("Start Fluent Mesh")
        run_directory = Path(self.config.run_directory).resolve()
        run_directory.mkdir(parents=True, exist_ok=True)
        session = cast(
            MeshingSession,
            pyfluent.launch_fluent(
                mode=pyfluent.FluentMode.MESHING,
                precision=pyfluent.Precision.DOUBLE,
                processor_count=self.config.processor_count,
                ui_mode="gui",
                cwd=str(run_directory),
                cleanup_on_exit=self.config.cleanup_on_exit,
            ),
        )
        self.meshing_session = session
        self.watertight = session.watertight()
        print_color("End Fluent Mesh")

    def _import_geometry(self, geometry_file: str) -> None:
        print_color("Start Import Geometry")
        import_geometry = self.watertight.import_geometry
        import_geometry.file_name.set_state(geometry_file)
        import_geometry.length_unit.set_state(self.config.length_unit)
        import_geometry()
        print_color("End Import Geometry")

    def _generate_surface_mesh(self) -> None:
        print_color("Start Generate Surface Mesh")
        create_surface_mesh = self.watertight.create_surface_mesh
        separation_yes_no = fluent_yes_no(self.config.separation_required)
        surface_mesh_args = {
            "cfd_surface_mesh_controls": {
                "max_size": self.config.surface_max_size,
                "min_size": 1,
            },
            "separation_required": separation_yes_no,
            "surface_mesh_preferences": {
                "sm_separation": separation_yes_no,
            },
        }
        if self.config.separation_required:
            surface_mesh_args["separation_angle"] = self.config.separation_angle
            surface_mesh_args["surface_mesh_preferences"][
                "sm_separation_angle"
            ] = self.config.separation_angle

        create_surface_mesh.arguments.update_dict(surface_mesh_args)
        create_surface_mesh()
        print_color("End Generate Surface Mesh")
        self._print_boundary_zone_debug("after_surface_mesh")

        if self.pause_config.enabled and self.pause_config.after_surface_mesh:
            pause_for_gui("表面メッシュ作成が完了しました。必要ならFluent GUIで確認・編集してください。")

    def _describe_geometry(self) -> None:
        print_color("Start Describe Geometry")
        describe_geometry = self.watertight.describe_geometry

        # setup_typeを変えると後続タスク構成が変わるため、段階的に反映する。
        describe_geometry.update_child_tasks(setup_type_changed=False)
        describe_geometry.arguments.update_dict(
            {
                "setup_type": self.config.geometry_setup_type,
            }
        )
        describe_geometry.update_child_tasks(setup_type_changed=True)
        describe_geometry.arguments.update_dict(
            {
                "setup_type": self.config.geometry_setup_type,
                "capping_required": fluent_yes_no(self.config.capping_required),
                "wall_to_internal": fluent_yes_no(self.config.wall_to_internal),
            }
        )
        describe_geometry.update_child_tasks(setup_type_changed=False)
        describe_geometry()
        print_color("End Describe Geometry")

    def _create_caps(self) -> None:
        for cap_setting in self.config.cap_settings:
            self._create_cap(cap_setting)

    def _create_cap(self, setting: CapSetting) -> None:
        """指定したzoneをcap化し、inlet/outletなどの境界タイプを割り当てる。"""

        print_color(f"Start Capping: {setting.name}")
        capping = get_workflow_task(
            self.watertight,
            display_name="Enclose Fluid Regions (Capping)",
            python_name="enclose_fluid_regions_capping",
        )
        capping_args = {
            "create_patch_preferences": {
                "show_create_patch_preferences": False,
            },
            "patch_name": setting.name,
            "zone_type": setting.zone_type,
            "selection_type": setting.selection_type,
            "zone_selection_list": setting.zones,
        }
        capping.arguments.update_dict(capping_args)

        # ZoneSelectionListを入れるとFluent側でZoneLocationが補完されることがある。
        current_args = capping.arguments.get_state(explicit_only=True)
        zone_location = current_args.get("zone_location")
        if zone_location:
            capping.arguments.update_dict({"zone_location": zone_location})

        capping.add_child_to_task()
        cap_task = capping.insert_compound_child_task()
        capping.arguments.set_state({})
        if cap_task is None:
            cap_task = self.watertight._task(setting.name)
        cap_task()
        print_color(f"End Capping: {setting.name}")

    def _create_regions(self) -> None:
        """capで閉じた開口を基に、Fluentに流体領域を検出させる。"""

        print_color("Start Create Regions")
        create_regions = get_workflow_task(
            self.watertight,
            display_name="Create Regions",
            python_name="create_regions",
        )
        create_regions.arguments.update_dict(
            {
                "number_of_flow_volumes": self.config.number_of_flow_volumes,
                "retain_dead_region_name": fluent_yes_no(
                    self.config.retain_dead_region_name
                ),
            }
        )
        create_regions()
        print_color("End Create Regions")

    def _update_regions(self) -> None:
        print_color("Start Update Regions")
        update_regions = get_workflow_task(
            self.watertight,
            display_name="Update Regions",
            python_name="update_regions",
        )
        update_regions()
        print_color("End Update Regions")

        if self.pause_config.enabled and self.pause_config.after_update_regions:
            pause_for_gui("Update Regionsが完了しました。必要ならFluent GUIで確認・編集してください。")

    def _update_boundaries(self) -> None:
        """Solverへ渡す境界名と境界タイプを明示する。"""

        for boundary_type in self.config.boundary_type_settings:
            self._update_boundary(boundary_type)

        self._print_boundary_zone_debug("after_update_boundaries")

        if self.pause_config.enabled and self.pause_config.after_update_boundaries:
            pause_for_gui("Update Boundariesが完了しました。境界一覧をFluent GUIで確認してください。")

    def _update_boundary(self, setting: BoundaryTypeSetting) -> None:
        """Meshing側のface zoneをSolver側の独立した境界として登録する。"""

        print_color(f"Start Update Boundary: {setting.name} -> {setting.zone_type}")
        update_boundaries = get_workflow_task(
            self.watertight,
            display_name="Update Boundaries",
            python_name="update_boundaries",
        )
        update_args: dict[str, object] = {
            "selection_type": setting.selection_type,
            "boundary_zone_list": setting.zones,
            "boundary_label_list": [setting.name],
            "boundary_label_type_list": [setting.zone_type],
        }
        if setting.old_name is not None:
            update_args["old_boundary_label_list"] = [setting.old_name]
        if setting.old_zone_type is not None:
            update_args["old_boundary_label_type_list"] = [setting.old_zone_type]

        self._execute_update_boundaries(update_boundaries, update_args, setting)
        print_color(f"End Update Boundary: {setting.name} -> {setting.zone_type}")

    def _execute_update_boundaries(
        self,
        update_boundaries,
        update_args: dict[str, object],
        setting: BoundaryTypeSetting,
    ) -> None:
        """2025R2のlegacy workflowと新しめのtyped workflowの両方を扱う。"""

        legacy_error: Exception | None = None
        try:
            update_boundaries.arguments.update_dict(update_args)
            update_boundaries()
            return
        except Exception as exc:
            legacy_error = exc

        try:
            for name, value in update_args.items():
                getattr(update_boundaries, name).set_state(value)
            update_boundaries()
            return
        except Exception as exc:
            raise RuntimeError(
                f"Failed to update boundary '{setting.name}' from zones "
                f"{setting.zones} to type '{setting.zone_type}'."
            ) from legacy_error or exc

    def _create_boundary_layers(self) -> None:
        for boundary_layer in self.config.boundary_layers:
            self._create_boundary_layer(boundary_layer)

        if self.pause_config.enabled and self.pause_config.after_boundary_layers:
            pause_for_gui("Add Boundary Layersが完了しました。必要ならFluent GUIで確認・編集してください。")

    def _create_boundary_layer(self, setting: BoundaryLayerSetting) -> None:
        """境界層制御を1つ追加して実行する。"""

        print_color(f"Start Add Boundary Layers: {setting.control_name}")
        add_boundary_layers = get_workflow_task(
            self.watertight,
            display_name=("Add Boundary Layers", "Add Boundary Layer"),
            python_name=("add_boundary_layers", "add_boundary_layer"),
        )
        boundary_layer_args: dict[str, object] = {
            "bl_control_name": setting.control_name
        }
        if setting.regions_type is not None:
            boundary_layer_args["face_scope"] = {
                "regions_type": setting.regions_type,
            }
        if setting.region_scope is not None:
            boundary_layer_args["region_scope"] = setting.region_scope
        if setting.number_of_layers is not None:
            boundary_layer_args["number_of_layers"] = setting.number_of_layers

        add_boundary_layers.arguments.update_dict(boundary_layer_args)

        # Compound taskは親タスクへ設定を入れたあと、子タスクを作成してその子を実行する。
        add_boundary_layers.add_child_to_task()
        boundary_layer_task = add_boundary_layers.insert_compound_child_task()
        add_boundary_layers.arguments.set_state({})

        if boundary_layer_task is None:
            boundary_layer_task = get_workflow_task(
                self.watertight,
                display_name=setting.control_name,
                python_name=setting.control_name,
            )

        boundary_layer_task.arguments.update_dict(boundary_layer_args)
        boundary_layer_task()
        print_color(f"End Add Boundary Layers: {setting.control_name}")

    def _generate_volume_mesh(self) -> None:
        print_color("Start Generate Volume Mesh")
        create_volume_mesh = get_workflow_task(
            self.watertight,
            display_name=("Generate the Volume Mesh", "Generate Volume Mesh"),
            python_name=(
                "create_volume_mesh_wtm",
                "create_volume_mesh",
                "generate_the_volume_mesh",
            ),
        )
        create_volume_mesh.arguments.update_dict({"volume_fill": self.config.volume_fill})
        create_volume_mesh()
        print_color("End Generate Volume Mesh")
        self._print_boundary_zone_debug("after_volume_mesh")

        if self.pause_config.enabled and self.pause_config.after_volume_mesh:
            pause_for_gui("Generate Volume Meshが完了しました。必要ならFluent GUIで確認・編集してください。")

    def _print_boundary_zone_debug(self, stage: str) -> None:
        """対象face zoneがMeshing側に残っているかを確認する。"""

        if not self.config.boundary_type_settings:
            return

        session = self._require_meshing_session()
        meshing_utilities = getattr(session, "meshing_utilities", None)
        if meshing_utilities is None:
            print_color(
                f"[{stage}] meshing_utilities is not available.",
                color="yellow",
            )
            return

        targets = self._boundary_debug_targets()
        print_color(f"[{stage}] Boundary zone debug", color="blue")
        for target in targets:
            exists = self._safe_meshing_query(
                lambda: meshing_utilities.boundary_zone_exists(zone_name=target)
            )
            zone_type = self._safe_meshing_query(
                lambda: meshing_utilities.get_zone_type(zone_name=target)
            )
            labels = self._safe_meshing_query(
                lambda: meshing_utilities.get_labels_on_face_zones(
                    face_zone_name_list=[target]
                )
            )
            print_color(
                f"[{stage}] {target}: exists={exists}, type={zone_type}, "
                f"labels={labels}",
                color="blue",
            )

        for pattern in self._boundary_debug_patterns(targets):
            matches = self._safe_meshing_query(
                lambda pattern=pattern: meshing_utilities.get_face_zones(
                    filter=pattern
                )
            )
            print_color(
                f"[{stage}] get_face_zones(filter={pattern!r}) -> {matches}",
                color="blue",
            )

    def _boundary_debug_targets(self) -> list[str]:
        targets: list[str] = []
        for setting in self.config.boundary_type_settings:
            for name in [setting.name, *setting.zones]:
                if name not in targets:
                    targets.append(name)
        return targets

    def _boundary_debug_patterns(self, targets: list[str]) -> list[str]:
        patterns: list[str] = []
        for target in targets:
            suffix = target.rsplit(":", maxsplit=1)[-1]
            pattern = f"*{suffix}*"
            if pattern not in patterns:
                patterns.append(pattern)
        return patterns

    def _safe_meshing_query(self, query):
        try:
            return query()
        except Exception as exc:
            return f"ERROR: {exc}"
