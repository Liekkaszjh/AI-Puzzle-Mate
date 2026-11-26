"""故事图谱的结构校验和查询；故事因果是否合理仍交给审核 Agent。"""
from copy import deepcopy

from llm import ModelError


NODE_KINDS = {"人物", "地点", "物品", "事件", "条件", "信息"}
RELATIONS = {"人物关系", "时间先后", "动机", "因果", "知情", "发生地点"}


class GraphError(ModelError):
    """图谱不能作为有效的故事事实底稿。"""


def _text(value, limit, label):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise GraphError("图谱%s必须是非空字符串且不超过%d字符" % (label, limit))
    return value.strip()


class StoryGraph:
    def __init__(self, data):
        if not isinstance(data, dict) or set(data) != {"nodes", "edges"}:
            raise GraphError("图谱必须且只能包含 nodes 和 edges")
        nodes, edges = data["nodes"], data["edges"]
        if not isinstance(nodes, list) or not 1 <= len(nodes) <= 100:
            raise GraphError("图谱必须包含1到100个节点")
        if not isinstance(edges, list) or len(edges) > 300:
            raise GraphError("图谱 edges 必须是最多300项的数组")
        self._nodes = {}
        self._edges = []
        for node in nodes:
            if not isinstance(node, dict) or set(node) != {"id", "kind", "text"}:
                raise GraphError("图谱节点必须且只能包含 id、kind、text")
            node_id = _text(node["id"], 64, "节点ID")
            kind = _text(node["kind"], 10, "节点类型")
            if kind not in NODE_KINDS:
                raise GraphError("图谱节点类型无效：" + kind)
            if node_id in self._nodes:
                raise GraphError("图谱节点ID重复：" + node_id)
            self._nodes[node_id] = {"id": node_id, "kind": kind, "text": _text(node["text"], 500, "节点描述")}
        seen = set()
        for edge in edges:
            if not isinstance(edge, dict) or set(edge) != {"source", "relation", "target"}:
                raise GraphError("图谱关系必须且只能包含 source、relation、target")
            source = _text(edge["source"], 64, "关系起点")
            target = _text(edge["target"], 64, "关系终点")
            relation = _text(edge["relation"], 10, "关系类型")
            if source not in self._nodes or target not in self._nodes:
                raise GraphError("图谱关系端点不存在：%s → %s" % (source, target))
            if relation not in RELATIONS:
                raise GraphError("图谱关系类型无效：" + relation)
            identity = (source, relation, target)
            if identity in seen:
                raise GraphError("图谱存在重复关系")
            seen.add(identity)
            self._edges.append(dict(source=source, relation=relation, target=target))

    def to_dict(self):
        return deepcopy({"nodes": list(self._nodes.values()), "edges": self._edges})

    def node(self, node_id):
        """按ID读取节点，返回副本以免调用方篡改图谱。"""
        return deepcopy(self._nodes[node_id])

    def outgoing(self, node_id, relation=None):
        """读取指定节点的出边，可按因果、动机等关系筛选。"""
        if node_id not in self._nodes:
            raise KeyError(node_id)
        return deepcopy([edge for edge in self._edges if edge["source"] == node_id
                         and (relation is None or edge["relation"] == relation)])

    def reachable(self, node_id, relation=None):
        """查询沿指定关系可达的节点；有环图也会终止，不做语义推断。"""
        if node_id not in self._nodes:
            raise KeyError(node_id)
        seen, pending, found = {node_id}, [node_id], []
        while pending:
            current = pending.pop(0)
            for edge in self.outgoing(current, relation):
                target = edge["target"]
                if target not in seen:
                    seen.add(target)
                    pending.append(target)
                    found.append(self.node(target))
        return found
