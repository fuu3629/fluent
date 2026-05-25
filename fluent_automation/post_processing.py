import csv
import math
import re
from pathlib import Path
from typing import Any, Callable, cast

from ansys.fluent.core.solver import Contour
from ansys.units.variable_descriptor import VariableCatalog

from fluent_automation.config import ContourImageSetting, PostProcessingConfig, SolverConfig
from fluent_automation.console import print_color


class PostProcessor:
    """解析結果のレポートと画像を出力する。"""

    def __init__(self, solver_session, solver_config: SolverConfig):
        self.solver_session = solver_session
        self.solver_config = solver_config
        self.config: PostProcessingConfig = solver_config.post_processing
        self.output_dir = Path(self.config.output_dir).resolve()

    def generate(self) -> None:
        if not self.config.enabled:
            return

        print_color("Start Post Processing")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        case_data_path = self._save_case_data()
        image_paths = self._save_contour_images()
        metrics = self._compute_metrics()
        metrics_path = self._write_metrics_csv(metrics)
        self._write_report(
            case_data_path=case_data_path,
            image_paths=image_paths,
            metrics=metrics,
            metrics_path=metrics_path,
        )
        print_color("End Post Processing")

    def _save_case_data(self) -> Path | None:
        if not self.config.save_case_data:
            return None

        case_data_path = self.output_dir / self.config.case_data_file_name
        try:
            self.solver_session.settings.file.write_case_data(
                file_name=str(case_data_path)
            )
            return case_data_path
        except Exception as exc:
            print_color(f"Failed to save case/data: {exc}", color="yellow")
            return None

    def _save_contour_images(self) -> list[Path]:
        image_paths: list[Path] = []
        for image_setting in self.config.contour_images:
            image_path = self._save_contour_image(image_setting)
            if image_path is not None:
                image_paths.append(image_path)

        return image_paths

    def _save_contour_image(self, image_setting: ContourImageSetting) -> Path | None:
        image_path = self.output_dir / image_setting.file_name
        try:
            contour_factory = cast(Any, Contour)
            contour = contour_factory(
                self.solver_session,
                new_instance_name=image_setting.name,
            )
            self._configure_contour(
                contour,
                field=image_setting.field,
                surfaces=self._resolve_contour_surfaces(
                    contour=contour,
                    configured_surfaces=image_setting.surfaces,
                ),
            )
            contour.display()

            graphics = self.solver_session.settings.results.graphics
            graphics.views.auto_scale()
            graphics.picture.save_picture(file_name=str(image_path))
            return image_path
        except Exception as exc:
            print_color(
                f"Failed to save contour image '{image_setting.file_name}': {exc}",
                color="yellow",
            )
            return None

    def _configure_contour(self, contour, field: str, surfaces: list[str]) -> None:
        contour_api = cast(Any, contour)
        contour_api.field = field
        contour_api.surfaces_list = surfaces
        contour_api.colorings.banded = True

    def _resolve_contour_surfaces(
        self,
        contour,
        configured_surfaces: list[str] | None,
    ) -> list[str]:
        if configured_surfaces is not None:
            return configured_surfaces

        allowed_surfaces = contour.surfaces_list.allowed_values()
        if not allowed_surfaces:
            raise RuntimeError("No surfaces are available for contour output.")

        return allowed_surfaces

    def _write_report(
        self,
        case_data_path: Path | None,
        image_paths: list[Path],
        metrics: dict[str, float],
        metrics_path: Path,
    ) -> None:
        report_path = self.output_dir / self.config.report_file_name
        lines = [
            "# Thermal Analysis Report",
            "",
            "## Solver Settings",
            "",
            f"- Length unit: {self.solver_config.length_unit}",
            f"- Energy equation: {self.solver_config.energy_enabled}",
            f"- Viscous model: {self.solver_config.viscous_model}",
            f"- K-omega model: {self.solver_config.k_omega_model or 'Fluent default'}",
            f"- Material: {self.solver_config.fluid_cell_zone_material}",
            f"- Iterations: {self.solver_config.iterations}",
            "",
            "## Boundary Conditions",
            "",
        ]

        inlet = self.solver_config.velocity_inlet
        if inlet is not None:
            lines.extend(
                [
                    f"- Inlet: {inlet.name}",
                    f"- Velocity specification: {inlet.velocity_specification_method}",
                    f"- Velocity magnitude: {inlet.velocity_magnitude} m/s",
                    f"- Turbulence specification: {inlet.turbulence_specification}",
                    f"- Hydraulic diameter: {inlet.hydraulic_diameter}",
                    f"- Temperature: {inlet.temperature} K",
                    "",
                ]
            )

        outlet = self.solver_config.pressure_outlet
        if outlet is not None:
            lines.extend(
                [
                    f"- Outlet: {outlet.name}",
                    f"- Gauge pressure: {outlet.gauge_pressure} Pa",
                    f"- Turbulence specification: {outlet.turbulence_specification}",
                    f"- Hydraulic diameter: {outlet.hydraulic_diameter}",
                    f"- Backflow total temperature: {outlet.backflow_temperature} K",
                    "",
                ]
            )

        for wall_heat_flux in self.solver_config.wall_heat_fluxes:
            lines.extend(
                [
                    f"- Wall heat flux: {wall_heat_flux.name}",
                    f"- Thermal condition: {wall_heat_flux.thermal_condition}",
                    f"- Heat flux: {wall_heat_flux.heat_flux} W/m^2",
                    "",
                ]
            )

        lines.extend(["## Result Summary", ""])
        lines.extend(self._report_metrics())
        lines.extend(["", "## Optimization Metrics", ""])
        lines.extend(self._format_metrics_for_report(metrics))

        lines.extend(["", "## Output Files", ""])
        if case_data_path is not None:
            lines.append(f"- Case/data: `{case_data_path}`")
        lines.append(f"- Metrics CSV: `{metrics_path}`")
        for image_path in image_paths:
            lines.append(f"- Image: `{image_path}`")

        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_metrics_csv(self, metrics: dict[str, float]) -> Path:
        metrics_path = self.output_dir / self.config.metrics_file_name
        with metrics_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(metrics.keys())
            writer.writerow(metrics.values())

        return metrics_path

    def _compute_metrics(self) -> dict[str, float]:
        metrics: dict[str, float] = {}

        inlet = self.solver_config.velocity_inlet
        outlet = self.solver_config.pressure_outlet
        if inlet is None or outlet is None:
            return metrics

        tin = self._resolve_inlet_temperature(inlet.name)
        pin = self._surface_area_weighted_value("pressure", inlet.name)
        pout = self._surface_area_weighted_value("pressure", outlet.name)
        delta_p = pin - pout

        metrics["Tin"] = tin
        metrics["Pin"] = pin
        metrics["Pout"] = pout
        metrics["deltaP"] = delta_p

        for index, wall_heat_flux in enumerate(self.solver_config.wall_heat_fluxes):
            wall_name = wall_heat_flux.name
            wall_area = self._surface_area(wall_name)
            tavg = self._surface_area_weighted_value(
                "temperature",
                wall_name,
            )
            q_total = wall_heat_flux.heat_flux * wall_area
            rth = (tavg - tin) / q_total

            metrics[f"Tavg_{wall_name}"] = tavg
            metrics[f"Area_{wall_name}"] = wall_area
            metrics[f"Q_{wall_name}"] = q_total
            metrics[f"Rth_{wall_name}"] = rth

            if index == 0:
                metrics["Tavg"] = tavg
                metrics["Q"] = q_total
                metrics["Rth"] = rth

        return metrics

    def _resolve_inlet_temperature(self, inlet_name: str) -> float:
        inlet = self.solver_config.velocity_inlet
        if inlet is not None and inlet.temperature is not None:
            return inlet.temperature

        return self._surface_area_weighted_value(
            "temperature",
            inlet_name,
        )

    def _surface_area(self, surface_name: str) -> float:
        return self._first_numeric_result(
            (
                lambda: self.solver_session.fields.reduction.area([surface_name]),
                lambda: self._surface_integral_value(
                    "area",
                    surface_names=[surface_name],
                ),
            ),
            f"area of {surface_name}",
        )

    def _surface_area_weighted_value(
        self,
        report_of: str,
        surface_name: str,
    ) -> float:
        expression_candidates = self._reduction_expression_candidates(report_of)
        report_of_candidates = self._surface_integral_field_candidates(report_of)

        getters: list[Callable[[], Any]] = []
        for expression in expression_candidates:
            getters.append(
                lambda expression=expression: self.solver_session.fields.reduction.area_average(
                    expression,
                    [surface_name],
                )
            )
        for field_name in report_of_candidates:
            getters.append(
                lambda field_name=field_name: self._surface_integral_value(
                    "area_weighted_avg",
                    report_of=field_name,
                    surface_names=[surface_name],
                )
            )

        return self._first_numeric_result(
            getters,
            f"area-weighted {report_of} on {surface_name}",
        )

    def _reduction_expression_candidates(self, report_of: str) -> list[Any]:
        if report_of == "pressure":
            return [
                VariableCatalog.PRESSURE,
                VariableCatalog.STATIC_PRESSURE,
                "StaticPressure",
            ]
        if report_of == "temperature":
            return [
                VariableCatalog.TEMPERATURE,
                VariableCatalog.WALL_TEMPERATURE,
                "StaticTemperature",
                "WallTemperature",
            ]

        return [report_of]

    def _surface_integral_field_candidates(self, report_of: str) -> list[str]:
        if report_of == "pressure":
            return ["pressure", "static-pressure", "absolute-pressure"]
        if report_of == "temperature":
            return ["temperature", "wall-temperature"]

        return [report_of]

    def _surface_integral_value(self, method_name: str, **kwargs) -> Any:
        surface_integrals = self.solver_session.settings.results.report.surface_integrals
        return self._call_surface_integral(surface_integrals, method_name, **kwargs)

    def _call_surface_integral(self, surface_integrals, method_name: str, **kwargs):
        """Call a surface-integral command across PyFluent naming variants."""
        method_names = [method_name]
        if method_name.startswith("get_"):
            method_names.append(method_name.removeprefix("get_"))
        else:
            method_names.append(f"get_{method_name}")

        for candidate_name in method_names:
            method = getattr(surface_integrals, candidate_name, None)
            if method is not None:
                value = method(**kwargs)
                if value is not None:
                    return value

        raise AttributeError(f"surface_integrals has no method for {method_name!r}")

    def _first_numeric_result(
        self,
        getters: tuple[Callable[[], Any], ...] | list[Callable[[], Any]],
        label: str,
    ) -> float:
        errors: list[str] = []
        for getter in getters:
            try:
                return self._extract_float(getter())
            except Exception as exc:
                errors.append(str(exc))

        raise ValueError(f"Could not compute {label}: {'; '.join(errors)}")

    def _extract_float(self, value: Any) -> float:
        if isinstance(value, bool):
            raise ValueError(f"Boolean value is not numeric: {value}")
        if isinstance(value, int | float):
            number = float(value)
            if math.isfinite(number):
                return number

        if isinstance(value, dict):
            preferred_keys = ("value", "result", "total", "net", "sum")
            for key in preferred_keys:
                if key in value:
                    return self._extract_float(value[key])
            for item in value.values():
                try:
                    return self._extract_float(item)
                except ValueError:
                    continue

        if isinstance(value, list | tuple):
            for item in reversed(value):
                try:
                    return self._extract_float(item)
                except ValueError:
                    continue

        if isinstance(value, str):
            match = re.search(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", value)
            if match is not None:
                return float(match.group(0))

        raise ValueError(f"Could not extract a numeric value from {value!r}")

    def _format_metrics_for_report(self, metrics: dict[str, float]) -> list[str]:
        if not metrics:
            return ["- Optimization metrics: unavailable"]

        return [f"- {name}: `{value}`" for name, value in metrics.items()]

    def _report_metrics(self) -> list[str]:
        outlet_name = (
            self.solver_config.pressure_outlet.name
            if self.solver_config.pressure_outlet is not None
            else None
        )
        inlet_name = (
            self.solver_config.velocity_inlet.name
            if self.solver_config.velocity_inlet is not None
            else None
        )

        lines = [
            self._format_metric(
                "Total sensible heat transfer",
                lambda: self.solver_session.settings.results.report.fluxes.get_heat_transfer_sensible(
                    zones="*"
                ),
            )
        ]

        if inlet_name is not None:
            lines.extend(
                [
                    self._format_surface_metric(
                        "Inlet area-weighted temperature",
                        "temperature",
                        "get_area_weighted_avg",
                        inlet_name,
                    ),
                    self._format_mass_flow_rate(
                        "Inlet mass flow rate",
                        inlet_name,
                    ),
                ]
            )

        if outlet_name is not None:
            lines.extend(
                [
                    self._format_surface_metric(
                        "Outlet mass-weighted temperature",
                        "temperature",
                        "get_mass_weighted_avg",
                        outlet_name,
                    ),
                    self._format_surface_metric(
                        "Outlet area-weighted velocity",
                        "velocity-magnitude",
                        "get_area_weighted_avg",
                        outlet_name,
                    ),
                    self._format_mass_flow_rate(
                        "Outlet mass flow rate",
                        outlet_name,
                    ),
                ]
            )

        return lines

    def _format_surface_metric(
        self,
        label: str,
        report_of: str,
        method_name: str,
        surface_name: str,
    ) -> str:
        surface_integrals = self.solver_session.settings.results.report.surface_integrals
        return self._format_metric(
            label,
            lambda: self._call_surface_integral(
                surface_integrals,
                method_name,
                report_of=report_of,
                surface_names=[surface_name],
            ),
        )

    def _format_mass_flow_rate(self, label: str, surface_name: str) -> str:
        surface_integrals = self.solver_session.settings.results.report.surface_integrals
        return self._format_metric(
            label,
            lambda: self._call_surface_integral(
                surface_integrals,
                "mass_flow_rate",
                surface_names=[surface_name],
            ),
        )

    def _format_metric(self, label: str, getter: Callable[[], Any]) -> str:
        try:
            value = getter()
            return f"- {label}: `{value}`"
        except Exception as exc:
            return f"- {label}: unavailable (`{exc}`)"
