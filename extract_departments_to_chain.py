"""
将人员部门信息从org_chart.json添加到complete_swiftwren_chain.json
"""
import json
from pathlib import Path
from typing import Any, Dict, List


def load_org_chart() -> Dict[str, Any]:
    """加载组织架构数据"""
    org_file = Path('VAST_Challenge_2026_MC2/org_chart.json')
    with open(org_file, encoding='utf-8') as f:
        return json.load(f)


def build_person_department_lookup(org: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """构建人员到部门的映射，支持多职位"""
    nodes = {node["id"]: node for node in org.get("nodes", [])}
    parent = {}
    for edge in org.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            parent[target] = source

    lookup = {}

    for node_id, node in nodes.items():
        if not str(node_id).startswith("person:"):
            continue

        # 查找所有部门（可能有多职位）
        departments = []
        teams = []

        # 向上遍历查找所有可能的部门
        cur = node_id
        visited = set()
        guard = 0

        while cur in parent and cur not in visited and guard < 20:
            visited.add(cur)
            cur = parent[cur]
            cur_node = nodes.get(cur, {})

            if cur_node.get("type") == "department":
                dept_name = str(cur_node.get("label", "Unknown"))
                if dept_name not in departments:
                    departments.append(dept_name)

            if cur_node.get("type") == "team":
                team_name = str(cur_node.get("label", ""))
                if team_name and team_name not in teams:
                    teams.append(team_name)

            guard += 1

        person_id = str(node_id).replace("person:", "")
        primary_dept = departments[0] if departments else "Unknown"

        lookup[person_id] = {
            "name": str(node.get("label", "")),
            "title": str(node.get("title", "")),
            "department": primary_dept,
            "departments": departments,  # 所有部门（多职位）
            "team": teams[0] if teams else ""
        }
        # 同时保存带Agent前缀的版本
        lookup[f"Agent/person:{person_id}"] = lookup[person_id]

    return lookup


def normalize_person_id(person_id: str) -> str:
    """规范化人员ID"""
    text = str(person_id).replace("Agent/", "")
    if text.startswith("person:"):
        return text.split(":")[1]
    # 如果是规范化名称（如"John Windward"），转换为ID格式
    if " " in text:
        return text.lower().replace(" ", "_")
    return text


def get_person_departments(person_identifier: str, department_lookup: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """获取人员部门信息 - 支持多种输入格式"""
    # 尝试直接查找
    if person_identifier in department_lookup:
        return department_lookup[person_identifier]

    # 如果是person:格式
    if person_identifier.startswith("person:"):
        person_id = person_identifier.replace("person:", "")
        if person_id in department_lookup:
            return department_lookup[person_id]

    # 如果是Agent/person:格式
    if person_identifier.startswith("Agent/person:"):
        person_id = person_identifier.replace("Agent/person:", "")
        if person_id in department_lookup:
            return department_lookup[person_id]

    # 如果是规范化名称格式（如"John Windward"）
    if " " in person_identifier:
        person_id = person_identifier.lower().replace(" ", "_")
        if person_id in department_lookup:
            return department_lookup[person_id]

    # 未找到
    return {
        "name": person_identifier,
        "department": "Unknown",
        "departments": ["Unknown"],
        "team": "",
        "title": ""
    }


def add_departments_to_chain(chain_data: Dict[str, Any], department_lookup: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """为链路数据中的每个事件添加部门信息"""
    events = chain_data["chain_events"]

    for event in events:
        # 提取人员信息
        parties = event.get("parties", [])
        source_agent = event.get("source_agent") or event.get("source_agent_raw", "")
        target_agent = event.get("target_agent") or event.get("target_agent_raw", "")

        # 为每个相关人员添加部门信息
        enriched_parties = []
        for party in parties:
            party_str = str(party)
            dept_info = get_person_departments(party_str, department_lookup)

            enriched_party = {
                "id": party,
                "name": dept_info.get("name", party_str),
                "department": dept_info.get("department", "Unknown"),
                "departments": dept_info.get("departments", ["Unknown"]),
                "team": dept_info.get("team", ""),
                "title": dept_info.get("title", "")
            }
            enriched_parties.append(enriched_party)

        event["parties_enriched"] = enriched_parties

        # 如果没有明确的source_agent，尝试从parties中提取第一个人员
        if not source_agent and parties:
            for party in parties:
                party_str = str(party)
                # 检查是否是人员（排除系统）
                if "person:" in party_str.lower() or "Agent/person:" in party_str:
                    source_agent = party_str
                    break
                # 如果是规范化人名（不包含系统关键词）
                elif " " in party_str and party_str not in ["Saidit", "File_system", "File System"]:
                    source_agent = party_str
                    break

        # 为source_agent添加部门信息
        if source_agent:
            dept_info = get_person_departments(source_agent, department_lookup)
            event["source_agent_department"] = dept_info.get("department", "Unknown")
            event["source_agent_departments"] = dept_info.get("departments", ["Unknown"])
            event["source_agent_name"] = dept_info.get("name", source_agent)

        # 如果没有明确的target_agent，尝试从parties中提取第二个人员
        if not target_agent and len(parties) > 1:
            found_first = False
            for party in parties:
                party_str = str(party)
                # 检查是否是人员（排除系统）
                if "person:" in party_str.lower() or "Agent/person:" in party_str:
                    if found_first:  # 如果已经找到第一个，这是第二个
                        target_agent = party_str
                        break
                    found_first = True
                # 如果是规范化人名
                elif " " in party_str and party_str not in ["Saidit", "File_system", "File System"]:
                    if found_first:
                        target_agent = party_str
                        break
                    found_first = True

        # 为target_agent添加部门信息
        if target_agent:
            dept_info = get_person_departments(target_agent, department_lookup)
            event["target_agent_department"] = dept_info.get("department", "Unknown")
            event["target_agent_departments"] = dept_info.get("departments", ["Unknown"])
            event["target_agent_name"] = dept_info.get("name", target_agent)

    return chain_data


def main():
    """主函数"""
    print("=" * 60)
    print("Adding Department Information to Chain Data")
    print("=" * 60)

    # 加载数据
    print("\n1. Loading data...")
    with open('result/complete_swiftwren_chain.json', encoding='utf-8') as f:
        chain_data = json.load(f)

    org = load_org_chart()
    department_lookup = build_person_department_lookup(org)
    print(f"   Loaded {len(department_lookup)} people from org chart")

    # 添加部门信息
    print("\n2. Adding department information...")
    enriched_chain = add_departments_to_chain(chain_data, department_lookup)

    # 保存更新后的数据
    print("\n3. Saving enriched data...")
    output_path = Path('result/complete_swiftwren_chain_with_departments.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(enriched_chain, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("Complete!")
    print("=" * 60)
    print(f"\nOutput: {output_path}")

    # 显示示例
    print("\nSample enriched events:")
    for event in enriched_chain["chain_events"][:3]:
        print(f"\n  Event {event.get('event_id')}: {event.get('short_name')}")
        if event.get('source_agent_department'):
            print(f"    Source: {event.get('source_agent_name')} ({event.get('source_agent_department')})")
        if event.get('target_agent_department'):
            print(f"    Target: {event.get('target_agent_name')} ({event.get('target_agent_department')})")

    # 统计部门覆盖
    departments = set()
    for event in enriched_chain["chain_events"]:
        if event.get('source_agent_department'):
            departments.add(event['source_agent_department'])
        if event.get('target_agent_department'):
            departments.add(event['target_agent_department'])

    print(f"\nDepartments covered: {sorted(departments)}")


if __name__ == '__main__':
    main()
