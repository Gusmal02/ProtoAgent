"""Trusted compiler output + constrained AST edits, NOT a hostile-code sandbox."""
import ast
import hashlib
from pathlib import Path
from .code_generator import sha

CALLS = {'set', 'type', 'len', 'dict', 'any', 'abs', 'ValueError', 'list', 'sorted',
         '_validate', '_unique_keys', 'solve', 'transform', 'validate_inputs'}
METHODS = {'values', 'items', 'get', 'setdefault', 'append', 'add'}


def check_source(source):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                             ast.With, ast.AsyncFunctionDef, ast.ClassDef, ast.While,
                             ast.Try)):
            raise ValueError('source outside trusted compiler subset')
        if isinstance(node, ast.Attribute) and node.attr not in METHODS:
            raise ValueError('attribute outside compiler subset')
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            raise ValueError('dunder name')
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id not in CALLS:
                raise ValueError('call outside compiler subset')
            if not isinstance(node.func, (ast.Name, ast.Attribute)):
                raise ValueError('indirect call')
    if any(not isinstance(n, ast.FunctionDef) for n in tree.body):
        raise ValueError('top-level functions only')
    return tree


def compose_project(base_files, generated_source):
    """Replace function bodies; unchanged functions/CLI are preserved by AST.

    Schema validation is generic compiler infrastructure; only the transform
    DAG is selected by search. No target-specific repair anchor is registered.
    """
    if set(base_files) != {'transforms.py', 'validation.py', 'cli.py'}:
        raise ValueError('project manifest')
    tree = check_source(generated_source)
    functions = {n.name: n for n in tree.body}
    if set(functions) != {'_validate', '_unique_keys', 'solve'}:
        raise ValueError('compiler function manifest')
    functions['solve'].name = 'transform'
    transform_tree = ast.parse(base_files['transforms.py'])
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'transform' for n in transform_tree.body):
        raise ValueError('missing editable function')
    kept = [n for n in transform_tree.body if not isinstance(n, ast.FunctionDef) or n.name not in {'transform', '_validate', '_unique_keys'}]
    transform_tree.body = kept + list(functions.values())
    validation_tree = ast.parse(base_files['validation.py'])
    validator = ast.parse(generated_source).body[0]
    validator.name = 'validate_inputs'
    if not any(isinstance(n, ast.FunctionDef) and n.name == 'validate_inputs' for n in validation_tree.body):
        raise ValueError('missing validator')
    validation_tree.body = [validator if isinstance(n, ast.FunctionDef) and n.name == 'validate_inputs' else n for n in validation_tree.body]
    result = dict(base_files)
    result['transforms.py'] = ast.unparse(ast.fix_missing_locations(transform_tree)) + '\n'
    result['validation.py'] = ast.unparse(ast.fix_missing_locations(validation_tree)) + '\n'
    return result


def check_project(base, files):
    if set(files)!=set(base) or set(base)!={'transforms.py','validation.py','cli.py'}:raise ValueError('project manifest')
    if files['cli.py']!=base['cli.py']:raise PermissionError('CLI is protected')
    for name,editable in [('transforms.py',{'transform','_validate','_unique_keys'}),('validation.py',{'validate_inputs'})]:
        old=ast.parse(base[name]);new=check_source(files[name])
        protected=lambda tree:[ast.dump(n) for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name not in editable]
        if protected(old)!=protected(new):raise PermissionError('protected function changed')
    return True


def publish_project_from_host(base_path, destination, base_hash, candidate, approved_hash, *, authorize):
    """Publish new directory only. Never overwrite the source or existing output.

    Caller supplies current authority; approved_hash must come from trusted
    review, not from an actor's claim. Directory creation is not multi-file
    atomic publication; completion marker is written last and verified on retry.
    """
    base_path, destination = Path(base_path), Path(destination)
    names = {'transforms.py', 'validation.py', 'cli.py'}
    if any((base_path / name).is_symlink() for name in names):
        raise ValueError('base symlink')
    base = {name: (base_path / name).read_text(encoding='utf8') for name in names}
    if sha(base) != base_hash or set(candidate['files']) != names:
        raise ValueError('stale base or manifest')
    if sha(candidate['files']) != candidate['hash'] or candidate['hash'] != approved_hash:
        raise PermissionError('approval binding')
    check_project(base,candidate['files'])
    if authorize() is not True:raise PermissionError('current publication authority')
    destination.mkdir(parents=True, exist_ok=False)
    for name, source in candidate['files'].items():
        with (destination / name).open('x', encoding='utf8', newline='\n') as stream:
            stream.write(source)
    if authorize() is not True:raise PermissionError('authority revoked before completion marker')
    with (destination / 'APPROVED.sha256').open('x', encoding='ascii') as stream:
        stream.write(approved_hash)
    return {'hash': approved_hash, 'destination': str(destination)}
