.DEFAULT_GOAL := help

DATA_FILE := callisto_core/wizard_builder/fixtures/wizard_builder_data.json

help:
	@perl -nle'print $& if m{^[a-zA-Z_-]+:.*?## .*$$}' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-25s\033[0m %s\n", $$1, $$2}'

clean:
	make clean-build
	make clean-lint

clean-build: ## clean the local files for a release
	rm -fr build/
	rm -fr dist/
	rm -fr *.egg-info
	rm -rf *.sqlite3
	rm -rf callisto_core/wizard_builder/tests/screendumps/
	rm -rf callisto_core/wizard_builder/tests/staticfiles/
	find callisto_core -name '*.pyc' -exec rm -f {} +
	find callisto_core -name '*.pyo' -exec rm -f {} +
	find callisto_core -name '*~' -exec rm -f {} +
	find callisto_core -type d -name "__pycache__" -exec rm -rf {} +

clean-lint: ## cleanup / display issues with isort and pep8
	autopep8 callisto_core/ -raai
	isort -rc callisto_core/
	make test-lint

test-lint: ## check style with pep8 and isort
	flake8 callisto_core/
	isort --check-only --diff --quiet -rc callisto_core/

test-suite:
	pytest -v --ignore=callisto_core/tests/delivery/test_frontend.py --ignore=callisto_core/wizard_builder/
	pytest -v callisto_core/wizard_builder/ --ignore=callisto_core/wizard_builder/tests/test_frontend.py --ignore=wizard_builder/tests/test_admin.py --ignore=wizard_builder/tests/test_migrations.py

test-integrated:
	pytest -v callisto_core/tests/delivery/test_frontend.py

test-fast: ## runs the test suite, with fast failures and a re-used database
	LOG_LEVEL=INFO pytest -v -l -s --maxfail=1 --ff --reuse-db --ignore=callisto_core/tests/delivery/test_frontend.py --ignore=callisto_core/wizard_builder/
	LOG_LEVEL=INFO pytest -v -l -s --maxfail=1 --ff --reuse-db callisto_core/wizard_builder/ --ignore=callisto_core/wizard_builder/tests/test_frontend.py --ignore=wizard_builder/tests/test_admin.py --ignore=wizard_builder/tests/test_migrations.py

test: ## run the linters and the test suite
	make test-lint
	make test-suite
	make test-integrated

release: ## package and upload a release
	make clean
	python setup.py sdist upload
	python setup.py bdist_wheel upload
	python setup.py tag
	make clean

pip-install:
	pip install -r callisto_core/requirements/dev.txt --upgrade

app-setup: ## setup the test application environment
	- rm wizard_builder_test_app.sqlite3
	- python manage.py flush --noinput
	python manage.py migrate --noinput --database default
	python manage.py create_admins
	python manage.py setup_sites
	python manage.py loaddata wizard_builder_data
	python manage.py loaddata callisto_core_notification_data
	python manage.py demo_user

dev-setup:
	make pip-install
	make app-setup

# Legacy from wizard_builder

osx-install:
	brew install git pyenv postgres chromedriver

test-local-suite:
	python manage.py check
	pytest -v --ignore callisto_core/wizard_builder/tests/test_frontend.py --ignore callisto_core/wizard_builder/tests/test_admin.py
	pytest -v callisto_core/wizard_builder/tests/test_frontend.py
	pytest -v callisto_core/wizard_builder/tests/test_admin.py

wizard-shell: ## manage.py shell_plus with dev settings
	DJANGO_SETTINGS_MODULE='callisto_core.wizard_builder.tests.test_app.dev_settings' python manage.py shell_plus

wizard-update-fixture: ## update fixture with migrations added on the local branch
	git checkout master
	- rm wizard_builder_test_app.sqlite3
	- python manage.py migrate
	- python manage.py loaddata $(DATA_FILE) -i
	git checkout @{-1}
	python manage.py migrate
	python manage.py dumpdata wizard_builder -o $(DATA_FILE)
	npx json -f $(DATA_FILE) -I

