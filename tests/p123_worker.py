"""Execute only sources admitted from the trusted local compiler in tests.

This child is not a security sandbox. No hostile plugins are evaluated here.
"""
import json
import runpy
import sys

config = json.load(sys.stdin)
if config.get('project'):
    sys.path.insert(0, config['folder'])
    from transforms import transform
    from validation import validate_inputs
    outputs = []
    for value in config['inputs']:
        validate_inputs(value)
        outputs.append(transform(value))
else:
    module = runpy.run_path(config['source'])
    outputs = [module['solve'](value) for value in config['inputs']]
print(json.dumps(outputs))
