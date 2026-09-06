import json
import copy

# Пути к файлам (поправь, если они лежат в других папках)
INPUT_FILE = 'contractors_audit.snapshot.json'
OUTPUT_FILE = 'synthetic_counterparties1.json'

# Справочник репутационных рисков для генерации
REP_DICT = {
    "fnsBlocking": {"chapter": "reestrs", "pos": "Нет блокировок счетов.",
                    "neg": "Есть блокировки банковских счетов по постановлениям ФНС."},
    "invalidAddress": {"chapter": "reestrs", "pos": "Адрес достоверен.",
                       "neg": "Находится в реестре организаций с фиктивным адресом."},
    "liquidationStatus": {"chapter": "reestrs", "pos": "Не в стадии банкротства.",
                          "neg": "Организация в процессе ликвидации/банкротства."},
    "disqualifiedAuthpersons": {"chapter": "manager", "pos": "Директор не дисквалифицирован.",
                                "neg": "Руководитель дисквалифицирован."},
    "dishonestProvider": {"chapter": "reestrs", "pos": "Нет в РНП.",
                          "neg": "Находится в реестре недобросовестных поставщиков."},
    "taxArrears": {"chapter": "reestrs", "pos": "Нет долгов по налогам.",
                   "neg": "Имеются крупные задолженности перед ФНС."},
    "arbitrationDefendant": {"chapter": "arbitr", "pos": "Нет судов в качестве ответчика.",
                             "neg": "Выступает ответчиком по арбитражным делам."},
    "executionProceedings": {"chapter": "execproc", "pos": "Нет открытых ИП.",
                             "neg": "Есть активные исполнительные производства."}
}

# 20 сюжетов для проверки нашего AI-Оценщика
SCENARIOS = [
    {
        "inn": "7700000001", "name": "ООО ИДЕАЛЬНЫЙ ГИГАНТ", "zsk": "GREEN", "risk": "LOW",
        "status": "CURRENT", "years": 20,
        "fin": [{"year": 2025, "rev": 5000000000, "profit": 1000000000},
                {"year": 2024, "rev": 4500000000, "profit": 800000000}],
        "arb": [], "exec": [], "rep_neg": [], "rep_pos": ["fnsBlocking", "liquidationStatus", "dishonestProvider"]
    },
    {
        "inn": "7700000002", "name": "ООО УВЕРЕННЫЙ СЕРЕДНЯК", "zsk": "GREEN", "risk": "LOW",
        "status": "CURRENT", "years": 5,
        "fin": [{"year": 2025, "rev": 15000000, "profit": 3000000}],
        "arb": [{"year": 2025, "p_cnt": 2, "p_amt": 500000, "d_cnt": 0, "d_amt": 0}],
        "exec": [], "rep_neg": [], "rep_pos": []
    },
    {
        "inn": "7700000003", "name": "ООО СВЕЖИЙ СТАРТАП", "zsk": "GREEN", "risk": "LOW",
        "status": "CURRENT", "years": 0,
        "fin": [], "arb": [], "exec": [], "rep_neg": [], "rep_pos": []
    },
    {
        "inn": "7700000004", "name": "ООО ОФИЦИАЛЬНЫЙ БАНКРОТ", "zsk": "RED", "risk": "HIGH",
        "status": "CLOSED", "status_reason": "Признание судом банкротом", "years": 8,
        "fin": [{"year": 2025, "rev": 0, "profit": -50000000, "payables": 150000000}],
        "arb": [], "exec": [], "rep_neg": ["liquidationStatus"], "rep_pos": []
    },
    {
        "inn": "7700000005", "name": "ООО ФИКТИВНАЯ КОНТОРА", "zsk": "RED", "risk": "HIGH",
        "status": "CURRENT", "years": 1,
        "fin": [{"year": 2025, "rev": 0, "profit": 0}],
        "arb": [], "exec": [], "rep_neg": ["invalidAddress", "taxArrears"], "rep_pos": []
    },
    {
        "inn": "7700000006", "name": "ООО ЖЕСТКИЙ НЕПЛАТЕЛЬЩИК", "zsk": "RED", "risk": "HIGH",
        "status": "CURRENT", "years": 3,
        "fin": [{"year": 2025, "rev": 1000000, "profit": -2000000}],
        "arb": [],
        "exec": [1000000, 2500000, 500000],  # Три исполнительных производства
        "rep_neg": ["fnsBlocking", "executionProceedings"], "rep_pos": []
    },
    {
        "inn": "7700000007", "name": "ООО ТОКСИЧНЫЙ РУКОВОДИТЕЛЬ", "zsk": "YELLOW", "risk": "MEDIUM",
        "status": "CURRENT", "years": 4,
        "fin": [{"year": 2025, "rev": 20000000, "profit": 1000000}],
        "arb": [], "exec": [], "rep_neg": ["disqualifiedAuthpersons"], "rep_pos": []
    },
    {
        "inn": "7700000008", "name": "ООО НЕДОБРОСОВЕСТНЫЙ ПОСТАВЩИК", "zsk": "YELLOW", "risk": "MEDIUM",
        "status": "CURRENT", "years": 6,
        "fin": [{"year": 2025, "rev": 40000000, "profit": 500000}],
        "arb": [{"year": 2025, "p_cnt": 0, "p_amt": 0, "d_cnt": 3, "d_amt": 15000000}],
        "exec": [], "rep_neg": ["dishonestProvider", "arbitrationDefendant"], "rep_pos": []
    },
    {
        "inn": "7700000009", "name": "ООО БОГАТЫЙ НО ЗАСУЖЕННЫЙ", "zsk": "GREEN", "risk": "MEDIUM",
        "status": "CURRENT", "years": 12,
        "fin": [{"year": 2025, "rev": 3000000000, "profit": 200000000}],
        "arb": [{"year": 2025, "p_cnt": 0, "p_amt": 0, "d_cnt": 1, "d_amt": 5000000000}],  # Иск больше выручки!
        "exec": [], "rep_neg": ["arbitrationDefendant"], "rep_pos": []
    },
    {
        "inn": "7700000010", "name": "ООО СУТЯЖНИК", "zsk": "GREEN", "risk": "LOW",
        "status": "CURRENT", "years": 7,
        "fin": [{"year": 2025, "rev": 50000000, "profit": 2000000}],
        "arb": [{"year": 2025, "p_cnt": 150, "p_amt": 30000000, "d_cnt": 0, "d_amt": 0}],  # Истец 150 раз
        "exec": [], "rep_neg": [], "rep_pos": []
    },
    {
        "inn": "7700000011", "name": "ООО РЕЗКОЕ ПАДЕНИЕ", "zsk": "YELLOW", "risk": "MEDIUM",
        "status": "CURRENT", "years": 5,
        "fin": [
            {"year": 2025, "rev": 2000000, "profit": -5000000},
            {"year": 2024, "rev": 100000000, "profit": 15000000},
            {"year": 2023, "rev": 500000000, "profit": 40000000}
        ],
        "arb": [], "exec": [], "rep_neg": [], "rep_pos": []
    },
    {
        "inn": "7700000012", "name": "ООО ЧУДО РОСТ", "zsk": "YELLOW", "risk": "MEDIUM",
        "status": "CURRENT", "years": 3,
        "fin": [
            {"year": 2025, "rev": 5000000000, "profit": 1000000},
            {"year": 2024, "rev": 0, "profit": 0},
            {"year": 2023, "rev": 0, "profit": 0}
        ],
        "arb": [], "exec": [], "rep_neg": [], "rep_pos": []
    },
    {
        "inn": "7700000013", "name": "ООО БРОШЕНКА", "zsk": "RED", "risk": "HIGH",
        "status": "CURRENT", "status_reason": "Предстоящее исключение из ЕГРЮЛ", "years": 10,
        "fin": [{"year": 2025, "rev": 0, "profit": 0}, {"year": 2024, "rev": 0, "profit": 0}],
        "arb": [], "exec": [], "rep_neg": ["invalidAddress"], "rep_pos": []
    },
    {
        "inn": "7700000014", "name": "ООО ПУСТЫШКА С ДОЛГАМИ", "zsk": "RED", "risk": "HIGH",
        "status": "CURRENT", "years": 4,
        "fin": [{"year": 2025, "rev": 0, "profit": -50000000, "payables": 50000000}],
        "arb": [], "exec": [5000000, 10000000], "rep_neg": ["executionProceedings"], "rep_pos": []
    },
    {
        "inn": "7700000015", "name": "ООО ПРОБЛЕМНЫЕ СВЯЗИ", "zsk": "GREEN", "risk": "MEDIUM",
        "status": "CURRENT", "years": 6,
        "fin": [{"year": 2025, "rev": 80000000, "profit": 5000000}],
        "arb": [], "exec": [], "rep_neg": [], "rep_pos": [],
        "related": [{"inn": "9999999999", "name": "ООО МАССОВЫЙ БАНКРОТ"}]
    },
    {
        "inn": "7700000016", "name": "ООО ЛИШЕНЦЫ", "zsk": "YELLOW", "risk": "MEDIUM",
        "status": "CURRENT", "years": 9,
        "fin": [{"year": 2025, "rev": 120000000, "profit": 10000000}],
        "arb": [], "exec": [], "rep_neg": [], "rep_pos": [],
        "licenses_expired": True
    },
    {
        "inn": "7700000017", "name": "ООО ТОЛЬКО ОТКРЫЛИСЬ", "zsk": "GREEN", "risk": "LOW",
        "status": "CURRENT", "years": 0,
        "fin": None, "arb": None, "exec": None, "rep_neg": [], "rep_pos": []
    },
    {
        "inn": "7700000018", "name": "ООО СМЕШАННЫЙ АРБИТРАЖ", "zsk": "GREEN", "risk": "MEDIUM",
        "status": "CURRENT", "years": 8,
        "fin": [{"year": 2025, "rev": 45000000, "profit": 2000000}],
        "arb": [{"year": 2025, "p_cnt": 5, "p_amt": 5000000, "d_cnt": 5, "d_amt": 5000000}],
        "exec": [], "rep_neg": ["arbitrationDefendant"], "rep_pos": []
    },
    {
        "inn": "7700000019", "name": "ООО ДОЛЖНИК ГОСУДАРСТВУ", "zsk": "YELLOW", "risk": "HIGH",
        "status": "CURRENT", "years": 5,
        "fin": [{"year": 2025, "rev": 60000000, "profit": 100000}],
        "arb": [], "exec": [], "rep_neg": ["taxArrears"], "rep_pos": []
    },
    {
        "inn": "7700000020", "name": "ООО КОРОЛЬ ХОЛДИНГОВ", "zsk": "GREEN", "risk": "LOW",
        "status": "CURRENT", "years": 15,
        "fin": [{"year": 2025, "rev": 10000000000, "profit": 2000000000}],
        "arb": [], "exec": [], "rep_neg": [], "rep_pos": [],
        "branches": 15, "capital": 5000000000
    }
]


def generate_synthetic_data():
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        original_data = json.load(f)

    # Берем первую карточку как эталонный скелет
    base_template = original_data[0]

    synthetic_dataset = []

    for s in SCENARIOS:
        # Делаем глубокую копию, чтобы не затереть шаблон
        company = copy.deepcopy(base_template)
        report = company['report']

        # Обновляем базовую инфу
        company['_id']['ogrn'] = s['inn'] + "000"
        report['baseInfo']['inn'] = s['inn']
        report['baseInfo']['shortName'] = s['name']
        report['baseInfo']['fullName'] = s['name']
        report['baseInfo']['riskLevel'] = s['risk']
        report['zskRiskLevel'] = s['zsk']
        report['baseInfo']['registrationInfo']['yearsFromRegistration'] = s['years']

        # Статус
        report['status']['status'] = s['status']
        if 'status_reason' in s:
            report['status']['reasonName'] = s['status_reason']
        elif 'reasonName' in report['status']:
            del report['status']['reasonName']

        # Капитал
        if 'capital' in s:
            report['foundersInfo']['shareCapital'] = s['capital']

        # Филиалы
        if 'branches' in s:
            report['branchesInfo'] = {"branchesCount": s['branches'], "branches": []}

        # Связанные компании
        if 'related' in s:
            report['relatedCompanies'] = s['related']
        else:
            report['relatedCompanies'] = []

        # Лицензии (Просроченные)
        if s.get('licenses_expired'):
            report['licenses'] = [{"number": "123", "name": "Лицензия", "status": "EXPIRED"}]
        else:
            report['licenses'] = []

        # Финансы (Безопасная для Pydantic структура)
        if s['fin'] is None:
            report['finReports'] = []
        else:
            fin_reports = []
            for f in s['fin']:
                payables = f.get('payables', 0)
                fin_reports.append({
                    "common": {"year": f['year'], "proceeds": f['rev'], "profit": f['profit']},
                    "assets": {
                        "totalAssets": f['rev'] // 2,
                        "currentAssets": {"total": f['rev'] // 4, "bankroll": 0},
                        "uncurrentAssets": {"total": f['rev'] // 4, "fixedAssets": 0}
                    },
                    "liabilities": {
                        "totalLiabilities": f['rev'] // 2,
                        "shortTermLiabilities": {"accountsPayable": payables, "total": payables}
                    }
                })
            report['finReports'] = fin_reports

        # Исполнительные производства (Добавили обязательную дату)
        if s['exec'] is None:
            report['executionProceedings'] = []
        else:
            exec_procs = []
            for i, amt in enumerate(s['exec']):
                exec_procs.append({
                    "active": True,
                    "number": f"12345/25/7700{i}-ИП",
                    "date": {"$date": "2025-06-01T21:00:00.000Z"},  # <- Вот это спасет парсер
                    "amount": amt
                })
            report['executionProceedings'] = exec_procs

        # Арбитраж
        if s['arb'] is None:
            report['arbitrationCases'] = []
        else:
            arb_cases = []
            for a in s['arb']:
                arb_cases.append({
                    "year": a['year'],
                    "plaintiffCount": a['p_cnt'], "plaintiffAmount": a['p_amt'],
                    "defendantCount": a['d_cnt'], "defendantAmount": a['d_amt']
                })
            report['arbitrationCases'] = arb_cases


        # Репутационные риски
        rep_risks = {"negative": [], "positive": []}
        for code in s['rep_neg']:
            if code in REP_DICT:
                rep_risks["negative"].append(
                    {"code": code, "name": REP_DICT[code]["neg"], "chapter": REP_DICT[code]["chapter"]})

        for code in s['rep_pos']:
            if code in REP_DICT:
                rep_risks["positive"].append(
                    {"code": code, "name": REP_DICT[code]["pos"], "chapter": REP_DICT[code]["chapter"]})

        report['reputationalRisks'] = rep_risks

        synthetic_dataset.append(company)

    # Сохраняем в файл
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(synthetic_dataset, f, ensure_ascii=False, indent=2)

    print(f"✅ Успешно сгенерировано {len(synthetic_dataset)} синтетических компаний!")
    print(f"💾 Файл сохранен по пути: {OUTPUT_FILE}")


if __name__ == "__main__":
    generate_synthetic_data()