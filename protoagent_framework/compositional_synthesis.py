"""Bounded compositional table synthesis. No target-specific pipelines or LLM.

Unary subprograms are retained independently of distance to the final target.
Observational deduplication is local to the current examples, not a universal
equivalence claim. Each CEGIS call rebuilds its classes, retaining total costs.
"""
import hashlib
import itertools
import time
from .typed_synthesis import canonical
from .typed_synthesis_v2 import apply
from .typed_synthesis_v3 import binary, compile_dag


class SearchStopped(RuntimeError):
    def __init__(self, status):
        self.status = status
        super().__init__(status)


class CompositionalSynthesizer:
    def __init__(self, candidates=200000, row_operations=12000000, seconds=20):
        self.cap = candidates
        self.row_cap = row_operations
        self.seconds = seconds
        self.used = self.rows_used = 0
        self.elapsed = 0.

    def synthesize(self, contract, examples):
        key, value = contract['key'], contract['value']
        names = contract['inputs']
        if key == value or not all(isinstance(x, str) and x.isidentifier() for x in (key, value)):
            raise ValueError('column identifiers')
        if not 2 <= len(names) <= 3 or len(set(names)) != len(names):
            raise ValueError('two or three distinct inputs')
        if not 1 <= len(examples) <= 32:
            raise ValueError('example bound')
        depth = contract.get('branch_depth', 3)
        if type(depth) is not int or not 0 <= depth <= 4:
            raise ValueError('branch depth')
        for example in examples:
            if set(example['input']) != set(names):
                raise ValueError('input names')
            for table in list(example['input'].values()) + [example['output']]:
                if type(table) is not list or len(table) > 100:
                    raise ValueError('table bound')
                if any(type(r) is not dict or set(r) != {key, value} or type(r[key]) is not str or type(r[value]) is not int or abs(r[value]) > 10000 for r in table):
                    raise ValueError('typed table schema')
        actions = [('filter_gt', n) for n in (-1, 0, 1)] + [('filter_lt', 0),
                   ('scale', -1), ('scale', 2), ('scale', 3), ('offset', -1),
                   ('offset', 1), ('unique', None), ('group_sum', None),
                   ('sort', False), ('sort', True)]
        targets = [e['output'] for e in examples]
        began = time.monotonic()

        def charge(states):
            cost = sum(len(rows) for rows in states)
            if self.used >= self.cap or self.rows_used + cost > self.row_cap or self.elapsed + time.monotonic() - began >= self.seconds:
                raise SearchStopped('search_budget_exhausted')
            self.used += 1
            self.rows_used += cost

        def result(expr):
            def swaps(node):
                if node[0]=='input':return []
                proposals=[]
                if node[0]=='unary':
                    inner=node[2]
                    if inner[0]=='unary' and {node[1][0],inner[1][0]}=={'unique','filter_gt'}:
                        proposals.append(('unary',inner[1],('unary',node[1],inner[2])))
                    proposals += [('unary',node[1],child) for child in swaps(inner)]
                else:
                    proposals += [('binary',node[1],child,node[3]) for child in swaps(node[2])]
                    proposals += [('binary',node[1],node[2],child) for child in swaps(node[3])]
                return proposals
            def measure(node,inputs):
                if node[0]=='input':return inputs[node[1]],0
                left,work=measure(node[2],inputs)
                if node[0]=='unary':return apply(left,node[1],key,value),work+len(left)
                right,rw=measure(node[3],inputs)
                return binary(left,right,node[1],key,value),work+rw+len(left)+len(right)
            quality=[]
            for variant in [expr]+swaps(expr)[:7]:
                def nodes(node):return 1 if node[0]=='input' else 1+nodes(node[2])+(nodes(node[3]) if node[0]=='binary' else 0)
                # Reserve a conservative row-work bound BEFORE profiling the
                # variant, including all its internal operations, not just input.
                charge([table for e in examples for table in e['input'].values()]*nodes(variant))
                measured=[measure(variant,e['input']) for e in examples]
                if [v[0] for v in measured]==targets:
                    quality.append((sum(v[1] for v in measured),canonical(variant),variant))
            expr=min(quality,key=lambda item:(item[0],item[1]))[2]
            source = compile_dag(expr, key, value)
            # The emitted native join enforces the same uniqueness precondition
            # as the interpreter. Input validation is not inferred authority.
            lines = source.splitlines()
            safe = [lines[0], '    _validate(inputs)']
            for line in lines[1:]:
                if line.startswith('    indexed = '):
                    # Determine branches from the emitted join expression.
                    right = line.split(' for r in ')[1].rstrip('}')
                    following = lines[lines.index(line) + 1]
                    left = following.split(' for r in ')[1].split(']')[0]
                    safe.append(f'    _unique_keys({left})')
                    safe.append(f'    _unique_keys({right})')
                safe.append(line)
            prelude = ('def _validate(inputs):\n'
                       f'    if type(inputs) is not dict or set(inputs) != set({tuple(names)!r}): raise ValueError("input names")\n'
                       '    for rows in inputs.values():\n'
                       '        if type(rows) is not list or len(rows) > 100: raise ValueError("table bound")\n'
                       f'        if any(type(r) is not dict or set(r) != set({(key,value)!r}) or type(r[{key!r}]) is not str or type(r[{value!r}]) is not int or abs(r[{value!r}]) > 10000 for r in rows): raise ValueError("typed table schema")\n'
                       'def _unique_keys(rows):\n'
                       f'    if len({{r[{key!r}] for r in rows}}) != len(rows): raise ValueError("join requires unique keys")\n')
            source = prelude + '\n'.join(safe) + '\n'
            return {'dag': expr, 'source': source, 'hash': hashlib.sha256(source.encode()).hexdigest(),
                    'candidates_total': self.used, 'row_operations_total': self.rows_used,
                    'search': 'bounded_factored_DAG', 'equivalence_scope': 'current_examples_only',
                    'quality':{'compatible_variants':len(quality),'selected_row_work':min(v[0] for v in quality),
                               'variant_row_work':[v[0] for v in quality],'policy':'correctness_then_declared_row_work_proxy'}}

        try:
            # All branch examples are compared with one another, NOT ranked by
            # resemblance to a final answer before the binary operation exists.
            pools = {}
            for name in names:
                initial = [e['input'][name] for e in examples]
                levels = [[(('input', name), initial)]]
                seen = {canonical(initial)}
                for _ in range(depth):
                    following = []
                    for expr, states in levels[-1]:
                        for action in actions:
                            charge(states)
                            child = [apply(rows, action, key, value) for rows in states]
                            if any(abs(r[value]) > 10**8 for rows in child for r in rows):
                                continue
                            identity = canonical(child)
                            if identity not in seen:
                                seen.add(identity)
                                following.append((('unary', action, expr), child))
                    levels.append(following)
                pools[name] = levels
            # Two disjoint dependency groups are composed. Three inputs use
            # the same binary combine recursively, not a reconciliation helper.
            if len(names) != 2:
                raise SearchStopped('capability_missing')
            # Meet-in-the-middle constraints for key-preserving arithmetic
            # joins. Build an index of observed right-branch values, projected
            # onto target keys. Missing keys retain native zero semantics;
            # extra right keys are harmless but the real expression is checked.
            # These are algebraic inverses of GENERIC operators, not a task route.
            target_maps = [{r[key]: r[value] for r in table} for table in targets]
            target_keys = [tuple(sorted(m)) for m in target_maps]
            indexes = {}
            if all(len(m) == len(t) for m, t in zip(target_maps, targets)):
                for name in names:
                    for level, pool in enumerate(pools[name]):
                        index = {}
                        for expr, states in pool:
                            charge(states)
                            maps = [{r[key]: r[value] for r in table} for table in states]
                            if any(len(m) != len(t) for m, t in zip(maps, states)):
                                continue
                            signature = tuple(tuple(m.get(k, 0) for k in keys) for m, keys in zip(maps, target_keys))
                            index.setdefault(signature, (expr, states))
                        indexes[name, level] = index
                posts = [None, ('sort', False), ('sort', True), ('unique', None),
                         ('scale', -1), ('scale', 2), ('scale', 3), ('offset', -1), ('offset', 1)]
                for cost in range(2 * depth + 1):
                    for left_depth in range(depth + 1):
                        right_depth = cost - left_depth
                        if not 0 <= right_depth <= depth:
                            continue
                        for left_name, right_name in itertools.permutations(names):
                            index = indexes[right_name, right_depth]
                            for left, states in pools[left_name][left_depth]:
                                charge(states)
                                maps = [{r[key]:r[value] for r in table} for table in states]
                                if any(len(m) != len(t) or set(m) != set(target) for m, t, target in zip(maps, states, target_maps)):
                                    continue
                                for post in posts:
                                    desired = []
                                    viable = True
                                    for target, keys in zip(target_maps, target_keys):
                                        row = []
                                        for k in keys:
                                            y = target[k]
                                            if post and post[0] == 'scale':
                                                if y % post[1]:viable=False;break
                                                y //= post[1]
                                            elif post and post[0] == 'offset':y -= post[1]
                                            row.append(y)
                                        desired.append(row)
                                    if not viable:
                                        continue
                                    for op, sign in (('join_subtract', -1), ('join_add', 1)):
                                        charge(states)
                                        required = tuple(tuple(sign * (y - m[k]) for k, y in zip(keys, values)) for m, keys, values in zip(maps, target_keys, desired))
                                        found = index.get(required)
                                        if not found:
                                            continue
                                        right, rs = found
                                        outputs = [binary(a,b,op,key,value) for a,b in zip(states,rs)]
                                        expr = ('binary',op,left,right)
                                        if post:
                                            outputs = [apply(table,post,key,value) for table in outputs]
                                            expr = ('unary',post,expr)
                                        if outputs == targets:
                                            return result(expr)
            for cost in range(2 * depth + 1):
                for left_depth in range(depth + 1):
                    right_depth = cost - left_depth
                    if not 0 <= right_depth <= depth:
                        continue
                    for left_name, right_name in itertools.permutations(names):
                        for left, ls in pools[left_name][left_depth]:
                            for right, rs in pools[right_name][right_depth]:
                                for op in ('concat', 'join_subtract', 'join_add'):
                                    charge(ls + rs)
                                    try:
                                        states = [binary(a, b, op, key, value) for a, b in zip(ls, rs)]
                                    except ValueError:
                                        continue
                                    expr = ('binary', op, left, right)
                                    if states == targets:
                                        return result(expr)
                                    for action in actions:
                                        charge(states)
                                        outputs = [apply(rows, action, key, value) for rows in states]
                                        if outputs == targets:
                                            return result(('unary', action, expr))
            raise SearchStopped('frontier_exhausted')
        finally:
            self.elapsed += time.monotonic() - began
