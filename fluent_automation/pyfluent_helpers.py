def fluent_yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def set_state(target, value: object, label: str) -> None:
    """PyFluent settingへ値を入れ、失敗時にどの設定か分かる例外にする。"""

    try:
        target.set_state(value)
    except Exception as exc:
        raise RuntimeError(f"Failed to set solver setting: {label}") from exc


def set_constant_value(target, value: object, label: str) -> None:
    """
    Fluentの "constant value" 形式の設定へ値を入れる。

    PyFluentの設定は、`target.value` を持つgroup、直接set_stateできるReal、
    `{option, value}` 形式のgroupが混在するため、順に試す。
    """

    last_error: Exception | None = None

    try:
        target.value.set_state(value)
        return
    except Exception as exc:
        last_error = exc

    try:
        target.set_state(value)
        return
    except Exception as exc:
        last_error = exc

    try:
        target.set_state({"option": "constant", "value": value})
        return
    except Exception as exc:
        last_error = exc

    raise RuntimeError(f"Failed to set constant solver setting: {label}") from last_error


def workflow_task_summary(watertight) -> list[str]:
    """RuntimeError用に現在のworkflow task一覧を文字列化する。"""

    task_names = []
    try:
        tasks = watertight.tasks(recompute=True)
    except Exception as exc:
        return [f"Workflow task list unavailable: {exc}"]

    for task in tasks:
        try:
            task_names.append(f"{task.python_name()} -> {task.display_name()}")
        except Exception:
            task_names.append(repr(task))
    return task_names


def get_workflow_task(
    watertight,
    display_name: str | tuple[str, ...],
    python_name: str | tuple[str, ...] | None = None,
):
    """
    workflow taskをPython名またはGUI表示名から取得する。

    PyFluent 25R2はlegacy workflowを使うため、同じGUI操作でもPython属性名が
    バージョンや生成順で揺れることがある。直に `watertight.xxx` へ依存せず、
    候補名を順に試す。
    """

    display_names = (display_name,) if isinstance(display_name, str) else display_name
    if python_name is None:
        python_names: tuple[str, ...] = ()
    elif isinstance(python_name, str):
        python_names = (python_name,)
    else:
        python_names = python_name

    for py_name in python_names:
        try:
            return getattr(watertight, py_name)
        except AttributeError:
            pass

    for name in display_names:
        try:
            return watertight._task(name)
        except Exception:
            pass

    for task in watertight.tasks(recompute=True):
        try:
            if task.display_name() in display_names:
                return task
            if task.python_name() in python_names:
                return task
        except Exception:
            continue

    task_list = "\n".join(f"  {name}" for name in workflow_task_summary(watertight))
    raise RuntimeError(
        f"Workflow task '{display_names[0]}' was not found.\n"
        "Describe Geometryの設定でこのタスクが生成されていない可能性があります。\n"
        f"Current workflow tasks:\n{task_list}"
    )
