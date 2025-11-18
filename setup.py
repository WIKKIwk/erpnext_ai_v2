from pathlib import Path
from setuptools import find_packages, setup


def load_requirements(path: str) -> list[str]:
	requirements: list[str] = []
	for line in Path(path).read_text(encoding="utf-8").splitlines():
		entry = line.strip()
		if not entry or entry.startswith("#"):
			continue
		requirements.append(entry)
	return requirements


# get version from __version__ variable in erpnext_ai/__init__.py
def get_version():
	init_file = Path(__file__).parent / "erpnext_ai" / "__init__.py"
	for line in init_file.read_text(encoding="utf-8").splitlines():
		if line.startswith("__version__"):
			return line.split("=")[1].strip().strip('"').strip("'")
	return "0.0.1"

version = get_version()

setup(
	name="erpnext_ai",
	version=version,
	description="AI assistant and reporting for ERPNext admins",
	author="Codex Assistant",
	author_email="codex@example.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=load_requirements("requirements.txt"),
)
