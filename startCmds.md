# Atlas Start Commands

## Create a virtual environment

```bash
python -m venv .venv
```

## Activate the environment

```bash
.venv\Scripts\activate
```

## Install dependencies

```bash
pip install -r requirements.txt
```

## Run Atlas once

```bash
python main.py
```

## Run Atlas in watch mode

```bash
python main.py --watch
```

## Run tests

```bash
python -m unittest discover -s tests -v
```

## Rebuild reports

```bash
python main.py
```

## Clean workspace outputs

```powershell
Remove-Item -Recurse -Force workspace\Reports\* , logs\* , workspace\Shortlisted\* , workspace\Maybe\* , workspace\Rejected\*
```
