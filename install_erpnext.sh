#!/usr/bin/env bash
# ========================================================================
# ERPNext Auto Installer for Ubuntu 22.04/24.04 LTS
# ------------------------------------------------------------------------
# This script sets up a fresh ERPNext bench with a single site.
# It installs system dependencies, configures MariaDB, installs Bench via
# pipx, fetches Frappe/ERPNext (version-15 by default) and provisions a site.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/WIKKIwk/erpnext_ai/master/install_erpnext.sh | sudo bash
# or download the file and run:
#   sudo bash install_erpnext.sh
#
# Customise by exporting environment variables before running, e.g.
#   export TARGET_USER=frappe
#   export SITE_NAME=erp.mycompany.local
#   sudo bash install_erpnext.sh
#
# Environment variables:
#   TARGET_USER            System user that will own the bench (default: frappe)
#   TARGET_USER_PASSWORD   Password for TARGET_USER (created if user missing)
#   FRAPPE_BRANCH          Frappe branch to checkout (default: version-15)
#   ERPNEXT_BRANCH         ERPNext branch to checkout (default: version-15)
#   BENCH_NAME             Bench directory name (default: frappe-bench)
#   SITE_NAME              Bench site name (default: erp.localhost)
#   SITE_DOMAIN            Optional site domain; defaults to SITE_NAME
#   SITE_ADMIN_PASSWORD    Administrator password (default: Admin@123)
#   MYSQL_ROOT_PASSWORD    MariaDB root password (default: dbroot)
#   NODE_MAJOR_VERSION     Node.js major version (default: 18)
#   PYTHON_VERSION         Python version to use (default: python3.10)
#   INSTALL_PRODUCTION     If "true", run bench setup production (default: false)
# ========================================================================

set -euo pipefail
IFS=$'\n\t'

log()   { printf '==> %s\n' "$*"; }
warn()  { printf 'WARNING: %s\n' "$*" >&2; }
fatal() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log_warn() { warn "$@"; }

require_root() {
	if [[ "${EUID}" -ne 0 ]]; then
		fatal "Run this script with sudo/root privileges."
	fi
}

ensure_commands() {
	for cmd in "$@"; do
		if ! command -v "${cmd}" >/dev/null 2>&1; then
			fatal "Required command '${cmd}' not found."
		fi
	done
}

run_as_target() {
	local target_user="$1"
	shift
	sudo -H -u "${target_user}" bash -lc "export PATH=\"\$HOME/.local/bin:\$PATH\"; $*"
}

normalize_python_spec() {
	local spec="$1"
	if [[ "${spec}" =~ ^python[0-9]+\.[0-9]+$ ]]; then
		printf '%s\n' "${spec}"
	elif [[ "${spec}" =~ ^[0-9]+\.[0-9]+$ ]]; then
		printf 'python%s\n' "${spec}"
	else
		printf '%s\n' "${spec}"
	fi
}

create_target_user() {
	local user="$1"
	local password="$2"
	if id "${user}" >/dev/null 2>&1; then
		log "User ${user} already exists."
		return
	fi
	log "Creating user ${user}."
	if [[ -n "${password}" ]]; then
		useradd --create-home --shell /bin/bash "${user}"
		echo "${user}:${password}" | chpasswd
	else
		useradd --create-home --shell /bin/bash "${user}"
		passwd -l "${user}" >/dev/null 2>&1 || true
	fi
}

configure_locale() {
	if [[ -x /usr/sbin/locale-gen ]]; then
		log "Ensuring UTF-8 locale availability."
		locale-gen en_US.UTF-8 >/dev/null 2>&1 || true
	fi
}

install_apt_dependencies() {
	local node_major="$1"
	local python_pkg="$2"
	log "Installing system packages via apt."
	export DEBIAN_FRONTEND=noninteractive
	apt-get update

	apt-get install -y software-properties-common

	# MariaDB root password pre-seed to avoid interactive prompt
	debconf-set-selections <<<"mariadb-server mysql-server/root_password password ${MYSQL_ROOT_PASSWORD}"
	debconf-set-selections <<<"mariadb-server mysql-server/root_password_again password ${MYSQL_ROOT_PASSWORD}"

	local base_packages=(
		build-essential
		curl
		git
		mariadb-server
		mariadb-client
		python3-pip
		python3-wheel
		redis-server
		xvfb
		libfontconfig1
		libfreetype6
		libjpeg-dev
		liblcms2-dev
		libtiff-dev
		libwebp-dev
		libx11-6
		libxext6
		libxrender1
		libharfbuzz0b
		libfribidi0
		wkhtmltopdf
		pipx
		apt-transport-https
		ca-certificates
		gnupg
	)

	local python_packages=(
		"${python_pkg}"
		"${python_pkg}-dev"
		"${python_pkg}-venv"
	)

	if ! apt-get install -y "${base_packages[@]}" "${python_packages[@]}"; then
		log_warn "Primary apt install failed; attempting to enable deadsnakes PPA and retry."
		if ! grep -Rqs "deadsnakes" /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null; then
			add-apt-repository -y ppa:deadsnakes/ppa
		fi
		apt-get update
		apt-get install -y "${base_packages[@]}" "${python_packages[@]}"
	fi

	log "Setting up Node.js ${node_major}.x via NodeSource."
	curl -fsSL "https://deb.nodesource.com/setup_${node_major}.x" | bash -
	apt-get install -y nodejs
	npm install -g yarn
}

configure_mariadb() {
	log "Configuring MariaDB utf8mb4 settings."
	cat >/etc/mysql/mariadb.conf.d/99-erpnext.cnf <<'EOF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci

[mysql]
default-character-set = utf8mb4
EOF
	systemctl restart mariadb
}

secure_mariadb_root() {
	log "Securing MariaDB root account."
	mysql --protocol=socket -u root <<SQL || true
ALTER USER 'root'@'localhost' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';
FLUSH PRIVILEGES;
SQL
}

install_bench() {
	local target_user="$1"
	log "Installing Bench CLI for user ${target_user}."
	run_as_target "${target_user}" "pipx ensurepath"
	run_as_target "${target_user}" "pipx install frappe-bench"
}

init_bench() {
	local target_user="$1"
	local bench_name="$2"
	local frappe_branch="$3"
	local python="${PYTHON_VERSION}"
	log "Initialising bench '${bench_name}' (Frappe ${frappe_branch})."
	run_as_target "${target_user}" "bench init --frappe-branch ${frappe_branch} --python ${python} ${bench_name}"
}

install_erpnext_app() {
	local target_user="$1"
	local bench_dir="$2"
	local erpnext_branch="$3"
	local site_name="$4"
	local admin_password="$5"
	log "Fetching ERPNext (${erpnext_branch}) into ${bench_dir}."
	run_as_target "${target_user}" "cd ${bench_dir} && bench get-app --branch ${erpnext_branch} erpnext"

	log "Creating site ${site_name}."
	run_as_target "${target_user}" "cd ${bench_dir} && bench new-site ${site_name} --mariadb-root-password ${MYSQL_ROOT_PASSWORD} --admin-password ${admin_password}"

	log "Installing ERPNext on ${site_name}."
	run_as_target "${target_user}" "cd ${bench_dir} && bench --site ${site_name} install-app erpnext"
	run_as_target "${target_user}" "cd ${bench_dir} && bench --site ${site_name} enable-scheduler"
}

setup_production() {
	local target_user="$1"
	local bench_dir="$2"
	local bench_cmd="/home/${target_user}/.local/bin/bench"
	if [[ "${INSTALL_PRODUCTION}" != "true" ]]; then
		log "Skipping production setup (INSTALL_PRODUCTION=${INSTALL_PRODUCTION})."
		return
	fi
	if [[ ! -x "${bench_cmd}" ]]; then
		warn "Bench executable not found at ${bench_cmd}; cannot run production setup."
		return
	fi
	log "Configuring production supervisor/nginx services."
	"${bench_cmd}" setup production "${target_user}" --bench-path "${bench_dir}"
	systemctl enable --now supervisor
	systemctl restart supervisor
}

print_summary() {
	cat <<EOF

========================================================================
ERPNext installation complete!

Bench directory : ${BENCH_HOME}
Site name       : ${SITE_NAME}
Site URL        : ${SITE_DOMAIN:-${SITE_NAME}}
Admin password  : ${SITE_ADMIN_PASSWORD}
MariaDB root    : ${MYSQL_ROOT_PASSWORD}

Next steps:
  - Development mode: sudo -H -u ${TARGET_USER} bash -lc "cd ${BENCH_HOME} && bench start"
  - Production mode : bench setup production ${TARGET_USER}
  - Access Desk     : http://${SITE_DOMAIN:-${SITE_NAME}} (update hosts or DNS)

Remember to secure your server (firewall, TLS) before exposing it publicly.
========================================================================
EOF
}

# -------------------------------------------------------------------------
# Main execution
# -------------------------------------------------------------------------
require_root
configure_locale
ensure_commands curl adduser sudo

TARGET_USER="${TARGET_USER:-frappe}"
TARGET_USER_PASSWORD="${TARGET_USER_PASSWORD:-}"
FRAPPE_BRANCH="${FRAPPE_BRANCH:-version-15}"
ERPNEXT_BRANCH="${ERPNEXT_BRANCH:-version-15}"
BENCH_NAME="${BENCH_NAME:-frappe-bench}"
SITE_NAME="${SITE_NAME:-erp.localhost}"
SITE_DOMAIN="${SITE_DOMAIN:-${SITE_NAME}}"
SITE_ADMIN_PASSWORD="${SITE_ADMIN_PASSWORD:-Admin@123}"
MYSQL_ROOT_PASSWORD="${MYSQL_ROOT_PASSWORD:-dbroot}"
NODE_MAJOR_VERSION="${NODE_MAJOR_VERSION:-18}"
PYTHON_INPUT="${PYTHON_VERSION:-python3.10}"
PYTHON_VERSION="$(normalize_python_spec "${PYTHON_INPUT}")"
INSTALL_PRODUCTION="${INSTALL_PRODUCTION:-false}"

create_target_user "${TARGET_USER}" "${TARGET_USER_PASSWORD}"
PYTHON_PACKAGE="${PYTHON_VERSION}"
install_apt_dependencies "${NODE_MAJOR_VERSION}" "${PYTHON_PACKAGE}"
configure_mariadb
secure_mariadb_root
install_bench "${TARGET_USER}"
BENCH_HOME="/home/${TARGET_USER}/${BENCH_NAME}"
init_bench "${TARGET_USER}" "${BENCH_NAME}" "${FRAPPE_BRANCH}"
install_erpnext_app "${TARGET_USER}" "${BENCH_HOME}" "${ERPNEXT_BRANCH}" "${SITE_NAME}" "${SITE_ADMIN_PASSWORD}"
setup_production "${TARGET_USER}" "${BENCH_HOME}"
print_summary
