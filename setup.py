"""Explicit SDK payload; laboratory-only external graph adapters are excluded."""
import ast
import hashlib
import json
from pathlib import Path
from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist
MODULES={'adaptive_synthesis','capability_reuse','community','compositional_synthesis','compositional_generator','project_editing','__init__','contracts','api','wire','canary_adapter','conformance',
         'governed_sqlite','sqlite_connector','oracle_cache','proposals',
         'engine','session','state_codec','checkpoint_storage','resource_policy','telemetry','durable_counter','team','control_effects','obligations','work_budget',
         'memory_store','toolkit','native_tools','deliveries','workspace','collaboration','code_generator','programming_runtime','typed_synthesis','typed_synthesis_v2','typed_synthesis_v3','multifile_synthesis','reducer_store','runtime_config'}

RUNTIME_SOURCES={
    'generation_transaction':'framework/f8_next/generation_transaction.py',
    'durable_generation_transport':'framework/f8_next/durable_generation_transport.py',
    'verified_tool_memory':'framework/f8_next/verified_tool_memory.py',
    'library/proto_library':'core/proto_library.py',
    'library/proto_tool_catalog':'core/proto_tool_catalog.py',
    'library/contextual_memory':'core/contextual_memory.py',
    'library/resonant_library_runtime':'core/resonant_library_runtime.py',
    'library/hierarchical_resonant_library':'core/hierarchical_resonant_library.py',
}

class RuntimeImports(ast.NodeTransformer):
    def visit_ImportFrom(self,node):
        if node.module=='generation_transaction':node.module='protoagent_framework.generation_transaction'
        elif node.module and node.module.startswith('core.'):
            node.module='protoagent_framework.library.'+node.module.split('.',1)[1]
        return node

def motor_sources():
    """Only the transitive local import closure of the actual v3 motor."""
    root=Path(__file__).resolve().parent
    todo=['core.agent_proto_v3']; found={}
    while todo:
        name=todo.pop()
        if name in found: continue
        path=root/(name.replace('.','/')+'.py')
        if not path.is_file(): raise RuntimeError('missing motor dependency: '+name)
        source=path.read_text(encoding='utf-8-sig'); tree=ast.parse(source)
        found[name]=(path,source,tree)
        for node in ast.walk(tree):
            names=([node.module] if isinstance(node,ast.ImportFrom) and node.module else
                   [a.name for a in node.names] if isinstance(node,ast.Import) else [])
            todo.extend(n for n in names if n.startswith(('core.','memory.')) and n not in found)
    return found

class MotorImports(ast.NodeTransformer):
    def visit_ImportFrom(self,node):
        if node.module and node.module.startswith(('core.','memory.')):
            node.module='protoagent_framework.motor.'+node.module
        return node
    def visit_Import(self,node):
        for alias in node.names:
            if alias.name.startswith(('core.','memory.')):
                # Bare `import core.x` binds core; require explicit bindings.
                if alias.asname is None: raise RuntimeError('unbound namespace import: '+alias.name)
                alias.name='protoagent_framework.motor.'+alias.name
        return node

class SDKBuild(build_py):
    def find_package_modules(self, package, package_dir):
        return [m for m in super().find_package_modules(package,package_dir) if m[1] in MODULES]
    def run(self):
        super().run()
        package=Path(self.build_lib)/'protoagent_framework'
        (package/'library').mkdir(exist_ok=True)
        (package/'library/__init__.py').write_text('"""Evidence library, optional numeric dependencies; no host grants."""\n',encoding='utf8')
        runtime_manifest={}
        for name,relative in RUNTIME_SOURCES.items():
            source=(Path(__file__).resolve().parent/relative).read_text(encoding='utf-8-sig')
            generated=ast.unparse(RuntimeImports().visit(ast.parse(source)))+'\n'
            (package/(name+'.py')).write_text(generated,encoding='utf8')
            runtime_manifest[name]={'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'generated_sha256':hashlib.sha256(generated.encode()).hexdigest()}
        (package/'runtime_sources.json').write_text(json.dumps(runtime_manifest,indent=2),encoding='utf8')
        base=Path(self.build_lib)/'protoagent_framework'/'motor'
        for package in ('','core','memory'):
            folder=base/package; folder.mkdir(parents=True,exist_ok=True)
            (folder/'__init__.py').write_text('"""Packaged v3 motor; generated from audited source closure."""\n',encoding='utf8')
        manifest={}
        for name,(path,source,tree) in motor_sources().items():
            target=base/(name.replace('.','/')+'.py')
            generated=ast.unparse(MotorImports().visit(tree))+'\n'
            target.write_text(generated,encoding='utf8')
            manifest[name]={'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
                            'generated_sha256':hashlib.sha256(generated.encode()).hexdigest()}
        (base/'sources.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
class MotorSdist(sdist):
    def make_release_tree(self, base_dir, files):
        # The sdist must be able to reproduce the wheel without the checkout.
        files=list(files)
        for name,(path,_,_) in motor_sources().items():
            relative=str(path.relative_to(Path(__file__).resolve().parent))
            if relative not in files: files.append(relative)
        for relative in RUNTIME_SOURCES.values():
            if relative not in files:files.append(relative)
        super().make_release_tree(base_dir,files)
setup(cmdclass={'build_py':SDKBuild,'sdist':MotorSdist})
