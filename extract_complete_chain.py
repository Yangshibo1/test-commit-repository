"""
提取完整的SwiftWren链路数据
从Emma创建SwiftWren.txt开始，到John发帖、删帖结束
"""
import json
from pathlib import Path
from typing import Any, Dict, List
from datetime import datetime


def load_data() -> List[Dict[str, Any]]:
    """加载MC2原始数据"""
    data_file = Path('VAST_Challenge_2026_MC2/MC2 data.json')
    with open(data_file, encoding='utf-8') as f:
        mc2_data = json.load(f)
    return mc2_data.get('events', [])


def find_emma_creates(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """查找Emma创建的SwiftWren相关文件"""
    emma_creates = []
    for e in events:
        if e.get('short_name') == 'create_file':
            parties = e.get('parties', [])
            if any('emma_harbor' in str(p).lower() for p in parties):
                details = e.get('details', {})
                target = details.get('target', '')
                if 'SwiftWren' in target:
                    emma_creates.append({
                        'event_id': e.get('id'),
                        'short_name': e.get('short_name'),
                        'when': e.get('when'),
                        'datetime': e.get('datetime'),
                        'parties': parties,
                        'details': details,
                        'file_type': 'source' if 'SwiftWren.txt' == target else 'instructions'
                    })
    return emma_creates


def load_instruction_tasks() -> List[Dict[str, Any]]:
    """加载node_08中的186条指令任务"""
    node08_file = Path('VAST_Challenge_2026_MC2/src/node_08_similar_attempts.json')
    with open(node08_file, encoding='utf-8') as f:
        node08 = json.load(f)
    return node08.get('instruction_tasks', [])


def normalize_person(person_id: str) -> str:
    """规范化人员ID"""
    text = str(person_id).replace('Agent/', '')
    if text.startswith('person:'):
        parts = text.split(':')[1].split('_')
        return ' '.join(p.capitalize() for p in parts)
    if text.startswith('system:'):
        return text.split(':')[1].capitalize()
    return text


def format_instruction_task(task: Dict[str, Any], index: int) -> Dict[str, Any]:
    """格式化指令任务"""
    event = task.get('event', {})
    details = event.get('details', {})
    args = details.get('args', {})

    return {
        'index': index,
        'event_id': event.get('id'),
        'short_name': event.get('short_name'),
        'when': event.get('when'),
        'datetime': event.get('datetime'),
        'source_agent': normalize_person(task.get('source_agent', '')),
        'source_agent_raw': task.get('source_agent', ''),
        'target_agent': normalize_person(task.get('target_agent', '')),
        'target_agent_raw': task.get('target_agent', ''),
        'task': details.get('task', ''),
        'path': args.get('path', ''),
        'parties': event.get('parties', []),
        'details': details
    }


def find_key_events_around_post(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """查找发帖前后的关键事件"""
    key_event_ids = [373882, 373893, 373899, 373902]  # 关键事件ID
    key_events = []

    for e in events:
        if e.get('id') in key_event_ids:
            details = e.get('details', {})
            key_events.append({
                'event_id': e.get('id'),
                'short_name': e.get('short_name'),
                'when': e.get('when'),
                'datetime': e.get('datetime'),
                'parties': [normalize_person(p) for p in e.get('parties', [])],
                'details': details,
                'is_key': True
            })

    # 按时间排序
    key_events.sort(key=lambda x: x['when'] or 0)
    return key_events


def find_deletion_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """查找删除SwiftWren相关文件的事件"""
    deletions = []
    for e in events:
        if e.get('short_name') == 'delete_file':
            details = e.get('details', {})
            target = details.get('target', '')
            parties = e.get('parties', [])
            # 查找John Windward删除SwiftWren相关文件的事件
            if 'SwiftWren' in target and any('john_windward' in str(p).lower() for p in parties):
                deletions.append({
                    'event_id': e.get('id'),
                    'short_name': e.get('short_name'),
                    'when': e.get('when'),
                    'datetime': e.get('datetime'),
                    'parties': [normalize_person(p) for p in parties],
                    'details': details,
                    'file_target': target
                })
    return deletions


def find_post_event(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """查找目标发帖事件 (373902)"""
    for e in events:
        if e.get('id') == 373902:
            return {
                'event_id': e.get('id'),
                'short_name': e.get('short_name'),
                'when': e.get('when'),
                'datetime': e.get('datetime'),
                'parties': [normalize_person(p) for p in e.get('parties', [])],
                'details': e.get('details', {}),
                'is_key': True
            }
    return {}


def build_complete_chain() -> Dict[str, Any]:
    """构建完整的链路数据"""
    print("正在加载数据...")
    events = load_data()
    instruction_tasks = load_instruction_tasks()

    print("正在提取数据...")

    # 1. Emma创建的文件
    emma_creates = find_emma_creates(events)
    print(f"  找到{len(emma_creates)}条Emma创建的SwiftWren文件")

    # 2. 指令任务链
    formatted_tasks = []
    for i, task in enumerate(instruction_tasks, 1):
        formatted_tasks.append(format_instruction_task(task, i))
    print(f"  找到{len(formatted_tasks)}条指令任务")

    # 3. 发帖前后的关键事件
    key_events = find_key_events_around_post(events)
    print(f"  找到{len(key_events)}条关键事件")

    # 4. 删除事件
    deletions = find_deletion_events(events)
    print(f"  找到{len(deletions)}条删除事件")

    # 5. 目标发帖事件
    post_event = find_post_event(events)
    print(f"  找到目标发帖事件: {post_event.get('event_id')}")

    # 按时间排序所有事件
    all_events = []

    # 添加Emma创建文件事件
    for create in emma_creates:
        all_events.append({
            **create,
            'stage': 'file_creation',
            'sequence_order': len(all_events) + 1
        })

    # 添加指令任务
    for task in formatted_tasks:
        all_events.append({
            **task,
            'stage': 'task_delegation',
            'sequence_order': len(all_events) + 1
        })

    # 添加关键事件（去重：只添加不在instruction_tasks中的）
    instruction_task_ids = {task.get('event_id') for task in formatted_tasks}
    for event in key_events:
        if event.get('event_id') not in instruction_task_ids:
            all_events.append({
                **event,
                'stage': 'key_actions',
                'sequence_order': len(all_events) + 1
            })

    # 添加删除事件
    for deletion in deletions:
        all_events.append({
            **deletion,
            'stage': 'cleanup',
            'sequence_order': len(all_events) + 1
        })

    # 按时间排序
    all_events.sort(key=lambda x: x['when'] if x.get('when') is not None else 0)

    # 重新编号
    for i, event in enumerate(all_events, 1):
        event['chronological_order'] = i

    # 统计信息
    stats = {
        'total_events': len(all_events),
        'emma_creates': len(emma_creates),
        'instruction_tasks': len(formatted_tasks),
        'key_events': len(key_events),
        'deletions': len(deletions),
        'stages': {
            'file_creation': len([e for e in all_events if e.get('stage') == 'file_creation']),
            'task_delegation': len([e for e in all_events if e.get('stage') == 'task_delegation']),
            'key_actions': len([e for e in all_events if e.get('stage') == 'key_actions']),
            'cleanup': len([e for e in all_events if e.get('stage') == 'cleanup'])
        }
    }

    return {
        'chain_events': all_events,
        'statistics': stats,
        'meta': {
            'description': '完整的SwiftWren链路：从Emma创建文件到John发帖结束',
            'data_sources': ['MC2 data.json', 'node_08_similar_attempts.json'],
            'extraction_date': datetime.now().isoformat()
        }
    }


def main():
    """主函数"""
    print("=" * 60)
    print("提取完整的SwiftWren链路数据")
    print("=" * 60)

    chain_data = build_complete_chain()

    # 保存结果
    result_dir = Path('result')
    result_dir.mkdir(exist_ok=True)

    output_file = result_dir / 'complete_swiftwren_chain.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(chain_data, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("提取完成！")
    print("=" * 60)
    print(f"\n统计信息:")
    stats = chain_data['statistics']
    print(f"  总事件数: {stats['total_events']}")
    print(f"  Emma创建文件: {stats['emma_creates']}")
    print(f"  指令任务: {stats['instruction_tasks']}")
    print(f"  关键事件: {stats['key_events']}")
    print(f"  删除事件: {stats['deletions']}")
    print(f"\n阶段分布:")
    for stage, count in stats['stages'].items():
        print(f"  {stage}: {count}")
    print(f"\n结果已保存到: {output_file}")

    # 显示时间范围
    events = chain_data['chain_events']
    if events:
        first_when = events[0].get('when')
        last_when = events[-1].get('when')
        if first_when and last_when:
            first_time = datetime.fromtimestamp(first_when)
            last_time = datetime.fromtimestamp(last_when)
            print(f"\n时间范围: {first_time} 到 {last_time}")
            duration = last_when - first_when
            print(f"总时长: {duration:.2f}秒 ({duration/86400:.2f}天)")


if __name__ == '__main__':
    main()
