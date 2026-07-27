import json
import os
import re

SESSION_DIR = r"C:\Users\83734\Desktop\opentrace\test-commit-repository\.opentrace\session_20260630_172421_en"

# Additional replacements for remaining Chinese fragments and punctuation
FIX_REPLACEMENTS = [
    # Chinese punctuation to English
    ("、", ", "),
    ("，", ", "),
    ("。", ". "),
    ("；", "; "),
    ("：", ": "),
    ("！", "! "),
    ("？", "? "),
    ("“", "\""),
    ("”", "\""),
    ("‘", "'"),
    ("’", "'"),
    ("（", "("),
    ("）", ")"),
    ("【", "["),
    ("】", "]"),
    ("《", "<"),
    ("》", ">"),
    ("—", "-"),
    ("–", "-"),
    ("…", "..."),
    ("·", "."),
    ("~", "~"),
    # Remaining common words
    ("智能体", "agent"),
    ("多智能体", "multi-agent"),
    ("日志", "log"),
    ("子任务", "subtask"),
    ("帖子", "post"),
    ("文件", "file"),
    ("人员", "personnel"),
    ("人员画像", "personnel profile"),
    ("活动类型", "activity type"),
    ("敏感文件", "sensitive file"),
    ("访问次数", "access count"),
    ("指令来源", "instruction source"),
    ("内容来源", "content source"),
    ("行为模式", "behavior pattern"),
    ("怀疑等级", "suspicion level"),
    ("调查建议", "investigation recommendation"),
    ("数据集", "dataset"),
    ("小型中间", "small intermediate"),
    ("分析结果", "analysis result"),
    ("核心问题", "core question"),
    ("回答状态", "answer status"),
    ("证据节点", "evidence node"),
    ("事件链", "event chain"),
    ("事件链摘要", "event chain summary"),
    ("问题重构", "problem reconstruction"),
    ("根因假设", "root cause hypothesis"),
    ("分析缺口", "analysis gap"),
    ("后续分析", "subsequent analysis"),
    ("系统概览", "system overview"),
    ("历史重复实例", "historical repetition instance"),
    ("干预建议", "intervention recommendation"),
    ("完成情况", "completion status"),
    ("可视化", "visualization"),
    ("血缘", "lineage"),
    ("数据血缘", "data lineage"),
    ("刷新", "refresh"),
    ("验证", "verification"),
    ("会话", "session"),
    ("完整性", "integrity"),
    ("查找", "find"),
    ("类似", "similar"),
    ("实例", "instance"),
    ("异常", "anomalous"),
    ("异常发帖", "anomalous posting"),
    ("异常帖子", "anomalous post"),
    ("发布", "publish"),
    ("外泄", "leakage"),
    ("数据外泄", "data leakage"),
    ("检查", "check"),
    ("浏览", "browse"),
    ("访问", "access"),
    ("删除", "delete"),
    ("创建", "create"),
    ("读取", "read"),
    ("写入", "write"),
    ("修改", "modify"),
    ("处理", "process"),
    ("统计", "statistics"),
    ("排序", "sort"),
    ("降序", "descending"),
    ("升序", "ascending"),
    ("排列", "arrange"),
    ("计数", "count"),
    ("汇总", "summarize"),
    ("追溯", "trace"),
    ("追踪", "track"),
    ("定位", "locate"),
    ("识别", "identify"),
    ("判断", "determine"),
    ("评估", "evaluate"),
    ("分析", "analysis"),
    ("比较", "compare"),
    ("匹配", "match"),
    ("筛选", "filter"),
    ("聚合", "aggregate"),
    ("分组", "group"),
    ("去重", "deduplicate"),
    ("提取", "extract"),
    ("转换", "transform"),
    ("映射", "map"),
    ("关联", "associate"),
    ("包含", "contains"),
    ("等于", "equals"),
    ("存在", "exists"),
    ("为空", "is empty"),
    ("非空", "is not empty"),
    ("字段", "field"),
    ("属性", "attribute"),
    ("参数", "parameter"),
    ("路径", "path"),
    ("目录", "directory"),
    ("文本", "text"),
    ("长度", "length"),
    ("大小", "size"),
    ("名称", "name"),
    ("标识", "identifier"),
    ("详情", "details"),
    ("描述", "description"),
    ("状态", "status"),
    ("类型", "type"),
    ("时间", "time"),
    ("时间戳", "timestamp"),
    ("频率", "frequency"),
    ("数量", "quantity"),
    ("总数", "total"),
    ("次数", "times"),
    ("个", ""),
    ("条", ""),
    ("次", ""),
    ("份", ""),
    ("张", ""),
    ("项", ""),
    ("款", ""),
    ("章", ""),
    ("节", ""),
    ("段", ""),
    ("行", ""),
    ("列", ""),
    ("层", ""),
    ("级", ""),
    ("类", ""),
    ("种", ""),
    ("批", ""),
    ("组", ""),
    ("套", ""),
    ("台", ""),
    ("架", ""),
    ("艘", ""),
    ("辆", ""),
    ("架", ""),
    ("只", ""),
    ("头", ""),
    ("匹", ""),
    ("件", ""),
    ("把", ""),
    ("支", ""),
    ("根", ""),
    ("片", ""),
    ("块", ""),
    ("粒", ""),
    ("颗", ""),
    ("滴", ""),
    ("杯", ""),
    ("瓶", ""),
    ("罐", ""),
    ("盒", ""),
    ("包", ""),
    ("袋", ""),
    ("箱", ""),
    ("桶", ""),
    ("壶", ""),
    ("碗", ""),
    ("盘", ""),
    ("盆", ""),
    ("锅", ""),
    ("灶", ""),
    ("炉", ""),
    ("床", ""),
    ("桌", ""),
    ("椅", ""),
    ("凳", ""),
    ("柜", ""),
    ("箱", ""),
    ("橱", ""),
    ("架", ""),
    ("屏", ""),
    ("扇", ""),
    ("门", ""),
    ("窗", ""),
    ("墙", ""),
    ("柱", ""),
    ("梁", ""),
    ("顶", ""),
    ("底", ""),
    ("边", ""),
    ("角", ""),
    ("面", ""),
    ("心", ""),
    ("中", ""),
    ("内", ""),
    ("外", ""),
    ("上", ""),
    ("下", ""),
    ("左", ""),
    ("右", ""),
    ("前", ""),
    ("后", ""),
    ("东", ""),
    ("西", ""),
    ("南", ""),
    ("北", ""),
]

def fix_text(text):
    if not isinstance(text, str):
        return text
    for cn, en in FIX_REPLACEMENTS:
        text = text.replace(cn, en)
    return text

def fix_object(obj):
    if isinstance(obj, dict):
        return {fix_text(k): fix_object(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_object(v) for v in obj]
    elif isinstance(obj, str):
        return fix_text(obj)
    return obj

def has_chinese(text):
    if not isinstance(text, str):
        return False
    return bool(re.search(r'[一-鿿]', text))

# Process all files
all_files = []
for root, dirs, files in os.walk(SESSION_DIR):
    for f in files:
        all_files.append(os.path.join(root, f))

print(f"Total files: {len(all_files)}")
modified_count = 0

for filepath in all_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        if not has_chinese(content):
            continue

        try:
            data = json.loads(content)
            fixed = fix_object(data)
            new_content = json.dumps(fixed, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            new_content = fix_text(content)

        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            modified_count += 1
            print(f"Fixed: {os.path.relpath(filepath, SESSION_DIR)}")
    except Exception as e:
        print(f"Error: {filepath}: {e}")

print(f"\nDone. Fixed: {modified_count}")

# Final check
chinese_texts = set()
for root, dirs, files in os.walk(SESSION_DIR):
    for f in files:
        fp = os.path.join(root, f)
        try:
            with open(fp, 'r', encoding='utf-8') as file:
                content = file.read()
            matches = re.findall(r'[^\x00-\x7F]+', content)
            for m in matches:
                if re.search(r'[一-鿿]', m):
                    chinese_texts.add(m)
        except:
            pass

print(f"\nRemaining unique Chinese strings: {len(chinese_texts)}")
for text in sorted(chinese_texts, key=len, reverse=True)[:30]:
    print(text)
