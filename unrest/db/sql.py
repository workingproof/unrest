
from re import sub
from typing import Any
from asyncpg import InsufficientPrivilegeError  # type:ignore
from unrest import Unauthorized, context

class Fragment:
    def __init__(self, *args) -> None:
        self.template = args[0]
        self.params: dict = {}
        self.dependencies: dict[str, Fragment] = {}
        self.path = None
        self.label: str = None # type:ignore
        self.is_mutation = context._ctx._local # TODO: indirect access 
        for i, v in enumerate(args[1:]):
            if issubclass(type(v), Fragment):
                self.dependencies[str(i + 1)] = v
            else:
                self.params[str(i + 1)] = v


    def __str__(self):
        return str(SqlExpression(self))

    async def __call__(self):
        raise NotImplementedError()

    async def __aenter__(self):
        try:
            return await self()
        except InsufficientPrivilegeError:
            raise Unauthorized("Insufficient privileges to execute this query")
        
    async def __aexit__(self, type, value, traceback):
        pass

class SqlExpression:
    def __init__(self, frag: Fragment):
        self.blocks : dict[str, dict[str, str]] = {}
        self.expr: list[tuple[str, str]] = []
        self.args: list[Any] = []
        self.is_mutation = False
        self.add(frag)
        if self.is_mutation and context._ctx._global is False: # TODO: indirect access
            raise Unauthorized("Mutation in query context")

    def _hash(self, frag: Fragment):
        T = frag.template
        for k, v in frag.dependencies.items():
            T = sub(r"\$%s" % k, v.label, T)
        for k, v in frag.params.items():
            T = sub(r"\$%s" % k, str(v), T)
        return T

    def _rewrite(self, frag: Fragment):
        T = frag.template
        for k, v in frag.dependencies.items():
            T = sub(r"\$%s" % k, v.label, T)
        for k, v in frag.params.items():
            offset = len(self.args) + 1
            self.args.append(v)
            T = sub(r"\$%s" % k, "$%d" % offset, T)
        return T

    def add(self, frag: Fragment): 
        
        for v in frag.dependencies.values():
            self.add(v) 

        path = frag.path or ""
        if path not in self.blocks:
            self.blocks[path] = {}

        hash = self._hash(frag)
        if hash not in self.blocks[path]:
            label = path + "." + str(len(self.blocks[path]) + 1)
            label = sub(".", "__", label)
            self.blocks[path][hash] = label

            sql = self._rewrite(frag)
            self.expr.append((label, sql))

            self.is_mutation = self.is_mutation or frag.is_mutation
        frag.label = self.blocks[path][hash]

    def __str__(self):
        buf = []
        for i, tup in enumerate(self.expr):
            if i + 1 == len(self.expr):
                buf.append("\n-- %s\n%s" % tup)
            elif i == 0:
                buf.append("with %s as (\n%s\n)" % tup)
            else:
                buf.append(",\n%s as (\n%s\n)" % tup)
        return "\n".join([x for x in ("".join(buf)).split("\n") if x.strip()])

