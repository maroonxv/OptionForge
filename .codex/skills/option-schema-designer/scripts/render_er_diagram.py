from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess


DEFAULT_JAR_PATH = Path(r"C:\Users\hungyuk\tools\plantuml\plantuml.jar")


def resolve_java_path(which=shutil.which) -> str:
    java_path = which("java")
    if java_path is None:
        raise RuntimeError("Java 未安装或未加入 PATH，无法渲染 PlantUML 图。")
    return java_path


def ensure_plantuml_jar(jar_path: Path) -> Path:
    resolved = jar_path.expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"PlantUML jar 未找到: {resolved}")
    return resolved


def derive_output_path(source_file: Path, output_dir: Path) -> Path:
    return output_dir / f"{source_file.stem}.svg"


def render_diagram(
    source_file: Path,
    output_dir: Path,
    jar_path: Path = DEFAULT_JAR_PATH,
    java_path: str | None = None,
    runner=subprocess.run,
) -> Path:
    source_file = source_file.expanduser().resolve()
    if not source_file.exists():
        raise FileNotFoundError(f"PlantUML 源文件未找到: {source_file}")

    resolved_jar = ensure_plantuml_jar(jar_path)
    resolved_java = java_path or resolve_java_path()
    output_dir = output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    completed = runner(
        [resolved_java, "-jar", str(resolved_jar), "-pipe", "-tsvg"],
        input=source_file.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        error_output = "\n".join(
            part for part in [completed.stderr.strip(), completed.stdout.strip()] if part
        )
        lowered = error_output.lower()
        if "syntax" in lowered or "error line" in lowered or "parsing" in lowered:
            raise RuntimeError(f"PlantUML 语法错误: {error_output}")
        if "unable to access jarfile" in lowered:
            raise FileNotFoundError(f"PlantUML jar 无法访问: {resolved_jar}")
        raise RuntimeError(f"PlantUML 渲染失败: {error_output or '未知错误'}")

    output_path = derive_output_path(source_file, output_dir)
    output_path.write_text(completed.stdout, encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染 Chen notation 的 PlantUML E-R 图。")
    parser.add_argument("--input", required=True, type=Path, help="PlantUML 源文件路径")
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="SVG 输出目录",
    )
    parser.add_argument(
        "--jar-path",
        type=Path,
        default=DEFAULT_JAR_PATH,
        help="PlantUML jar 路径",
    )
    parser.add_argument(
        "--java-path",
        default=None,
        help="Java 可执行文件路径，默认从 PATH 中查找",
    )
    args = parser.parse_args()

    output_path = render_diagram(
        source_file=args.input,
        output_dir=args.output_dir,
        jar_path=args.jar_path,
        java_path=args.java_path,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
