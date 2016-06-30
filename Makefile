
test:
	@for x in `find rtclite | grep \.py$$ | grep -v __init__\.py | sed -e 's/\\//\\./g' | sed -e 's/\\.py$$//g'`; do echo $$x; python -m $$x --test; done

doc:
	@python htmlify.py

clean:
	@find rtclite -name "*.pyc" -delete
	@find rtclite -name "rfc*.py.txt" -delete
	@find rtclite -name "*.py.html" -delete
	@find rtclite -name "index.html" -delete
