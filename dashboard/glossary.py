"""지표·컬럼·분석 이름을 한글 라벨과 한 줄 설명으로 푼다. 화면 표시 전용.

숫자를 만들지 않는다 — analyses/ 가 낸 키를 사람이 읽을 이름으로 바꾸기만 한다.
모르는 키는 원래 이름을 그대로 돌려준다(빠진 게 있어도 화면이 안 깨진다).
"""
from __future__ import annotations

# headline 스칼라 키 → (한글 라벨, 한 줄 설명)
METRICS: dict[str, tuple[str, str]] = {
    # session_trend
    "sessions": ("세션 수", "기간 내 전체 세션(방문)의 수"),
    "pv_per_session": ("세션당 페이지뷰", "한 세션이 평균 몇 개 화면을 보는지"),
    "seconds_per_session": ("세션당 체류(초)", "한 세션이 평균 몇 초 머무는지"),
    "sessions_per_user": ("사용자당 세션", "한 사람이 평균 몇 번 방문하는지"),
    # screen_flow
    "mean_expected_steps": ("평균 기대 걸음 수",
                            "어떤 화면에서 시작해 앱을 떠나기까지 평균 몇 화면을 밟는지"),
    "mean_exit_prob": ("평균 이탈률", "화면 하나가 세션의 마지막 화면이 될 평균 확률"),
    # screen_dwell_rank
    "mean_seconds_per_visit": ("방문당 체류(초)", "화면을 한 번 방문할 때 평균 몇 초 머무는지"),
    "dwell_coverage": ("체류 측정 커버리지",
                       "체류시간이 실제로 기록된 방문의 비율(나머지는 미측정)"),
    # screen_pair_affinity
    "mutual_information": ("상호정보량(nats)",
                          "현재 화면을 알면 다음 화면을 얼마나 예측할 수 있는지(0이면 무관)"),
    "pairs": ("화면 쌍 수", "관측된 (현재→다음) 화면 쌍의 가짓수"),
    # cross_service_flow
    "cross_service_share": ("서비스 건너뛰기 비율",
                            "화면 이동 중 서로 다른 서비스로 넘어가는 비율"),
    "switch_entropy": ("전환 분산도(nats)",
                       "서비스를 건너뛸 때 목적지가 얼마나 여러 갈래로 흩어지는지"),
    # screen_communities
    "communities": ("군집 수", "함께 묶이는 화면 그룹의 개수(데이터가 작아 참고용)"),
    "modularity": ("군집 응집도", "화면 군집이 얼마나 뚜렷하게 나뉘는지(0~1)"),
    # click_distribution
    "clicks": ("클릭 수", "기간 내 사용자 클릭의 총수"),
    "clicks_per_visit": ("방문당 클릭 수", "화면 한 번 방문에 평균 몇 번 클릭하는지"),
    "unattributed_share": ("미귀속 클릭 비율",
                           "첫 화면 이전에 일어나 특정 화면에 못 붙은 클릭의 비율"),
    # conditional_flow
    "action_information": ("행동 정보량(nats)",
                           "현재 화면을 안 상태에서 '무엇을 눌렀나'를 더 알면 "
                           "다음 화면을 얼마나 더 아는지"),
    "no_click_share": ("무클릭 전환 비율", "클릭 없이 다음 화면으로 넘어간 전환의 비율"),
    # path_ranking
    "n": ("걸음 수 n", "경로의 길이(n걸음)"),
    "coverage": ("커버리지", "상위 200 컷 이후 이 결과가 실제로 덮는 비율"),
    "paths": ("고유 경로 수", "관측된 서로 다른 경로의 가짓수"),
    "distinct_dropped": ("잘린 경로 수", "상위 200 컷에 밀려 '(other)'로 접힌 경로의 수"),
    "top_path_share": ("최빈 경로 비중", "가장 흔한 경로 하나가 차지하는 비율"),
    # markov_order_test
    "excess_information": ("초과 정보량(nats)",
                           "직전 화면을 하나 더 알면 다음 화면 예측이 얼마나 나아지는지"
                           "(0이면 1차 마르코프로 충분)"),
    "contexts": ("검정 문맥 수", "1차 가정을 검정한 3-gram 문맥의 수"),
    "diverging_context_share": ("1차 어긋난 문맥 비중",
                                "직전 화면이 예측을 유의하게 바꾸는 문맥의 물량 비중"),
}

# 표 컬럼 → 한글 라벨
COLUMNS: dict[str, str] = {
    "state": "화면",
    "from_state": "현재 화면",
    "to_state": "다음 화면",
    "prev_state": "직전 화면",
    "next_state": "다음 화면",
    "from_service": "출발 서비스",
    "to_service": "도착 서비스",
    "cnt": "건수",
    "share": "비중",
    "share_of_origin": "출발지 대비 비중",
    "exit_prob": "이탈률",
    "pi": "체류 비중(정상분포)",
    "expected_steps": "기대 걸음 수",
    "p_reach_exit": "이탈 도달 확률",
    "entropy": "다음화면 불확실성",
    "hhi": "집중도(HHI)",
    "top_p": "최빈 다음화면 확률",
    "effective_choices": "유효 선택지 수",
    "out_degree": "나가는 화면 수",
    "top_to": "가장 흔한 다음 화면",
    "pagerank": "중심도(PageRank)",
    "visits": "방문 수",
    "pmi": "결합강도(PMI)",
    "divergence": "발산(KL)",
    "path": "경로",
    "period": "날짜",
    "uv": "순방문자",
    "pv": "페이지뷰",
    "sessions": "세션 수",
    "events": "이벤트 수",
    "duration_sum": "체류합(초)",
    "seconds_per_visit": "방문당 체류(초)",
    "dwell_coverage": "체류 커버리지",
    "check_name": "검사",
    "violated": "위반 수",
    "total": "전체",
    "ratio": "위반율",
    "service_code": "서비스",
    "screen": "화면",
    "action_kind": "행동 종류",
    "layer1": "슬롯1",
    "layer2": "슬롯2",
    "k": "걸음 수 k",
    "p_hit": "도달 확률",
}

# 분석 이름 → 한 줄 설명(이 분석이 무엇을 보여주는가)
ANALYSES: dict[str, str] = {
    "session_trend": "기간별 세션·페이지뷰·체류시간이 어떻게 변하는지.",
    "screen_flow": "화면별로 얼마나 머물고 어디서 떠나는지, 어느 화면이 흐름의 중심인지.",
    "screen_dwell_rank": "화면별 방문당 체류시간 순위.",
    "screen_pair_affinity": "어떤 (현재→다음) 화면 쌍이 특별히 자주 붙는지 — 빈도가 아니라 결합 강도.",
    "cross_service_flow": "서비스 사이를 얼마나, 어디로 오가는지.",
    "reachability": "특정 화면에서 다른 화면까지 몇 걸음 안에 닿을 확률.",
    "screen_communities": "함께 묶이는 화면 그룹(군집).",
    "quality_report": "데이터 품질 검사(체류 누락·화면 없는 세션 등)별 위반 추이.",
    "click_distribution": "화면 안에서 무엇을 누르는지 — 클릭 분포.",
    "conditional_flow": "어떤 행동이 다음 화면을 결정하는지.",
    "path_ranking": "사용자가 밟는 n걸음 경로의 순위.",
    "markov_order_test": "다음 화면이 현재 화면만으로 정해지는지(1차 마르코프), "
                         "아니면 직전 화면도 알아야 하는지 검정.",
}


def metric_label(key: str) -> str:
    """headline 키의 한글 라벨. 모르면 키 그대로."""
    return METRICS.get(key, (key, ""))[0]


def metric_help(key: str) -> str:
    """headline 키의 한 줄 설명. 모르면 빈 문자열."""
    return METRICS.get(key, (key, ""))[1]


def column_label(col: str) -> str:
    """표 컬럼의 한글 라벨. 모르면 컬럼 이름 그대로."""
    return COLUMNS.get(col, col)


def analysis_desc(name: str) -> str:
    """분석의 한 줄 설명. 모르면 빈 문자열."""
    return ANALYSES.get(name, "")
