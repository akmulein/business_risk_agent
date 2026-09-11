const databaseName = process.env.MONGO_DATABASE || "counterparties";
const sourceCollectionName = process.env.MONGO_COLLECTION || "reports";
const readCollectionName = process.env.MONGO_READ_COLLECTION || "counterparty_cards";
const temporaryCollectionName = readCollectionName + "_building";

const database = db.getSiblingDB(databaseName);
const source = database.getCollection(sourceCollectionName);
const temporary = database.getCollection(temporaryCollectionName);

function asArray(value) {
  if (value === null || value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function asText(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text || null;
}

function asIsoDate(value) {
  if (value === null || value === undefined) return null;
  return value instanceof Date ? value.toISOString() : String(value);
}

function asNumber(value) {
  return value === null || value === undefined || value === "" ? null : value;
}

function compact(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => item !== null && item !== undefined),
  );
}

function itemId(reportId, type, index, suffix) {
  return [reportId, type, index, suffix].filter(
    (part) => part !== null && part !== undefined && part !== "",
  ).join(":");
}

function commonItem(reportId, inn, type, index, suffix) {
  return {
    id: itemId(reportId, type, index, suffix),
    report_id: reportId,
    company_inn: inn,
    subject_inn: inn,
    item_type: type,
    item_index: index,
  };
}

function buildStructureItems(report, reportId, inn) {
  const result = [];
  const founders = asObject(report.foundersInfo);

  asArray(founders.cofounders).forEach((value, index) => {
    const founder = asObject(value);
    result.push(compact({
      ...commonItem(reportId, inn, "founder", index),
      name: founder.name,
      related_inn: asText(founder.inn),
      role: "founder",
      share: asNumber(founder.share),
      amount: asNumber(founder.amount),
      date_from: asIsoDate(founder.dateFrom),
      active: founder.active ?? founder.isActive,
      details_json: founder,
    }));
  });

  const auth = asObject(founders.authPerson);
  if (Object.keys(auth).length) {
    result.push(compact({
      ...commonItem(reportId, inn, "director", 0),
      name: auth.name,
      related_inn: asText(auth.inn),
      role: "director",
      position: auth.positionName,
      date_from: asIsoDate(auth.positionDate),
      details_json: auth,
    }));
  }

  asArray(founders.parentOrganizations).forEach((value, index) => {
    const parent = asObject(value);
    result.push(compact({
      ...commonItem(reportId, inn, "parent_organization", index),
      name: parent.fullName,
      related_inn: asText(parent.inn),
      related_ogrn: asText(parent.ogrn),
      role: "parent_organization",
      date_from: asIsoDate(parent.parentDate),
      details_json: parent,
    }));
  });

  asArray(report.relatedCompanies).forEach((value, index) => {
    const related = asObject(value);
    const relatedInn = asText(related.inn);
    result.push(compact({
      ...commonItem(reportId, inn, "related_company", index),
      name: related.name,
      related_inn: relatedInn,
      related_ogrn: asText(related.ogrn),
      role: "related_company",
      registration_date: asIsoDate(related.registrationDate),
      auth_person_name: related.authPersonName,
      auth_person_position: related.authPersonPosition,
      details_json: related,
    }));

    asArray(related.parentOrganizations).forEach((parentValue, parentIndex) => {
      const parent = asObject(parentValue);
      result.push(compact({
        ...commonItem(
          reportId,
          inn,
          "related_parent_organization",
          parentIndex,
          relatedInn || index,
        ),
        subject_inn: relatedInn,
        name: parent.fullName,
        related_inn: asText(parent.inn),
        related_ogrn: asText(parent.ogrn),
        role: "parent_of_related_company",
        date_from: asIsoDate(parent.parentDate),
        details_json: parent,
      }));
    });
  });

  const activities = asObject(report.kindsOfActivityInfo);
  const mainActivity = asObject(activities.mainKindOfActivity);
  if (Object.keys(mainActivity).length) {
    result.push(compact({
      ...commonItem(reportId, inn, "activity", 0),
      role: "main",
      code: asText(mainActivity.code),
      description: mainActivity.description,
      details_json: mainActivity,
    }));
  }

  asArray(activities.otherKindsOfActivity).forEach((value, offset) => {
    const activity = asObject(value);
    const index = offset + 1;
    result.push(compact({
      ...commonItem(reportId, inn, "activity", index),
      role: "other",
      code: asText(activity.code),
      description: activity.description,
      details_json: activity,
    }));
  });

  const branches = asObject(report.branchesInfo);
  asArray(branches.branches).forEach((value, index) => {
    const branch = asObject(value);
    result.push(compact({
      ...commonItem(reportId, inn, "branch", index),
      name: branch.name,
      role: "branch",
      address: branch.address,
      details_json: branch,
    }));
  });

  asArray(report.phones).forEach((value, index) => {
    const phone = asObject(value);
    result.push(compact({
      ...commonItem(reportId, inn, "phone", index),
      role: "phone",
      phone_type: phone.phoneType,
      phone_code: asText(phone.phoneCode),
      phone_number: asText(phone.phoneNumber),
      details_json: phone,
    }));
  });

  asArray(report.taxSystem).forEach((value, index) => {
    const tax = asObject(value);
    result.push(compact({
      ...commonItem(reportId, inn, "tax_system", index),
      name: tax.fullName,
      role: "tax_system",
      code: asText(tax.shortName),
      details_json: tax,
    }));
  });

  return result;
}

function buildFinancialReports(report, reportId, inn) {
  const coefficientsByYear = new Map();
  asArray(report.coefficient).forEach((value) => {
    const coefficient = asObject(value);
    if (coefficient.year !== null && coefficient.year !== undefined) {
      coefficientsByYear.set(Number(coefficient.year), coefficient);
    }
  });

  const result = [];
  const financialYears = new Set();
  asArray(report.finReports).forEach((value) => {
    const financial = asObject(value);
    const common = asObject(financial.common);
    if (common.year === null || common.year === undefined) return;

    const year = Number(common.year);
    financialYears.add(year);
    const assets = asObject(financial.assets);
    const current = asObject(assets.currentAssets);
    const uncurrent = asObject(assets.uncurrentAssets);
    const liabilities = asObject(financial.liabilities);
    const longTerm = asObject(liabilities.longTermDuties);
    const shortTerm = asObject(liabilities.shortTermLiabilities);
    const coefficient = coefficientsByYear.get(year) || {};

    result.push(compact({
      report_id: reportId,
      company_inn: inn,
      year,
      proceeds: asNumber(common.proceeds),
      profit: asNumber(common.profit),
      total_assets: asNumber(assets.totalAssets),
      current_assets_total: asNumber(current.total),
      stocks: asNumber(current.stocks),
      receivables: asNumber(current.receivables),
      bankroll: asNumber(current.bankroll),
      uncurrent_assets_total: asNumber(uncurrent.total),
      fixed_assets: asNumber(uncurrent.fixedAssets),
      total_liabilities: asNumber(liabilities.totalLiabilities),
      capitals: asNumber(liabilities.capitals),
      long_term_duties_total: asNumber(longTerm.total),
      long_term_duties_others: asNumber(longTerm.others),
      short_term_liabilities_total: asNumber(shortTerm.total),
      borrowed_funds: asNumber(shortTerm.borrowedFunds),
      accounts_payable: asNumber(shortTerm.accountsPayable),
      sustainability: asNumber(coefficient.sustainability),
      solvency: asNumber(coefficient.solvency),
      profitability: asNumber(coefficient.profitability),
    }));
  });

  coefficientsByYear.forEach((coefficient, year) => {
    if (financialYears.has(year)) return;
    result.push(compact({
      report_id: reportId,
      company_inn: inn,
      year,
      sustainability: asNumber(coefficient.sustainability),
      solvency: asNumber(coefficient.solvency),
      profitability: asNumber(coefficient.profitability),
    }));
  });

  return result;
}

function buildRiskFactors(report, reportId, inn) {
  const result = [];
  const risks = asObject(report.reputationalRisks);
  ["negative", "positive"].forEach((sign) => {
    asArray(risks[sign]).forEach((value, index) => {
      const factor = asObject(value);
      if (!factor.name) return;
      result.push(compact({
        report_id: reportId,
        company_inn: inn,
        sign,
        item_index: index,
        code: factor.code,
        name: factor.name,
        chapter: factor.chapter,
      }));
    });
  });
  return result;
}

function buildArbitration(report, reportId, inn) {
  const result = [];

  asArray(report.arbitrationCases).forEach((value, index) => {
    const arbitrationCase = asObject(value);
    [
      ["plaintiff", arbitrationCase.plaintiffCount, arbitrationCase.plaintiffAmount],
      ["defendant", arbitrationCase.defendantCount, arbitrationCase.defendantAmount],
    ].forEach(([role, count, amount]) => {
      if (count === null || count === undefined) return;
      result.push(compact({
        id: itemId(reportId, "arbitration_yearly", index, role),
        report_id: reportId,
        company_inn: inn,
        source: "yearly",
        year: arbitrationCase.year === null || arbitrationCase.year === undefined
          ? null : Number(arbitrationCase.year),
        role,
        case_status: "all",
        case_count: Number(count),
        amount: asNumber(amount),
      }));
    });
  });

  const byStatus = asObject(report.arbitrationByStatus);
  if (byStatus.commonCount !== null && byStatus.commonCount !== undefined) {
    result.push(compact({
      id: itemId(reportId, "arbitration_status", 0, "all"),
      report_id: reportId,
      company_inn: inn,
      source: "status",
      role: "all",
      case_status: "all",
      case_count: Number(byStatus.commonCount),
      amount: asNumber(byStatus.commonAmount),
    }));
  }

  const mappings = [
    ["plaintiff", "finished", "plaintiffArbitration", "plaintiffArbitrationFinished", "pfCount", "pfAmount"],
    ["plaintiff", "appealed", "plaintiffArbitration", "plaintiffArbitrationAppealed", "paCount", "paAmount"],
    ["plaintiff", "pending", "plaintiffArbitration", "plaintiffArbitrationPending", "ppCount", "ppAmount"],
    ["defendant", "finished", "defandantArbitration", "defandantArbitrationFinished", "dfCount", "dfAmount"],
    ["defendant", "appealed", "defandantArbitration", "defandantArbitrationAppealed", "daCount", "daAmount"],
    ["defendant", "pending", "defandantArbitration", "defandantArbitrationPending", "dpCount", "dpAmount"],
  ];

  mappings.forEach((mapping, index) => {
    const [role, caseStatus, sideKey, statusKey, countKey, amountKey] = mapping;
    const block = asObject(asObject(byStatus[sideKey])[statusKey]);
    if (block[countKey] === null || block[countKey] === undefined) return;
    result.push(compact({
      id: itemId(reportId, "arbitration_status", index + 1, role + "_" + caseStatus),
      report_id: reportId,
      company_inn: inn,
      source: "status",
      role,
      case_status: caseStatus,
      case_count: Number(block[countKey]),
      amount: asNumber(block[amountKey]),
    }));
  });

  return result;
}

function buildLegalEvents(report, reportId, inn) {
  const result = [];

  asArray(report.executionProceedings).forEach((value, index) => {
    const event = asObject(value);
    result.push(compact({
      report_id: reportId,
      company_inn: inn,
      event_type: "execution",
      item_index: index,
      external_id: asText(event.number),
      event_date: asIsoDate(event.date),
      active: event.active,
      amount: asNumber(event.amount),
      details_json: event,
    }));
  });

  asArray(report.inspections).forEach((value, index) => {
    const event = asObject(value);
    result.push(compact({
      report_id: reportId,
      company_inn: inn,
      event_type: "inspection",
      item_index: index,
      external_id: asText(event.erpId),
      event_date: asIsoDate(event.startDate),
      end_date: asIsoDate(event.endDate),
      status: event.inspectionStatus,
      title: event.type,
      authority: event.authorityName,
      form: event.form,
      details_json: event,
    }));
  });

  asArray(report.licenses).forEach((value, index) => {
    const event = asObject(value);
    result.push(compact({
      report_id: reportId,
      company_inn: inn,
      event_type: "license",
      item_index: index,
      external_id: asText(event.number),
      event_date: asIsoDate(event.issueDate),
      end_date: asIsoDate(event.endDate),
      status: event.status,
      title: event.name,
      authority: event.issuingAuthority,
      details_json: event,
    }));
  });

  return result;
}

function buildProcurements(report, reportId, inn) {
  const result = [];
  asArray(report.procurements).forEach((value, index) => {
    const item = asObject(value);
    if (item.procurementsYear === null || item.procurementsYear === undefined) return;
    result.push(compact({
      report_id: reportId,
      company_inn: inn,
      item_index: index,
      year: Number(item.procurementsYear),
      federal_law_code: asText(item.federalLawCode),
      tender_admitted_count: asNumber(item.tenderAdmittedCnt),
      tender_winner_count: asNumber(item.tenderWinnerCnt),
      contract_signed_count: asNumber(item.contractSignedCnt),
      contract_signed_amount: asNumber(item.contractSignedAmt),
    }));
  });
  return result;
}

function buildCard(root) {
  const report = asObject(root.report);
  const base = asObject(report.baseInfo);
  const inn = asText(base.inn);
  if (!inn) throw new Error("Report " + EJSON.stringify(root._id) + " has no baseInfo.inn");

  const reportDate = asIsoDate(report.reportDate);
  const reportId = inn + ":" + (reportDate || "undated");
  const registration = asObject(base.registrationInfo);
  const status = asObject(report.status);
  const founders = asObject(report.foundersInfo);
  const branches = asObject(report.branchesInfo);

  return {
    _id: root._id,
    read_model_version: 1,
    source: {
      collection: sourceCollectionName,
      document_id: root._id,
    },
    company_reports: compact({
      report_id: reportId,
      report_date: reportDate,
      inn,
      ogrn: asText(base.ogrn),
      short_name: base.shortName,
      full_name: base.fullName,
      risk_level: base.riskLevel,
      zsk_risk_level: report.zskRiskLevel,
      kpp: asText(base.kpp),
      okpo: asText(base.okpo),
      address: base.address,
      email: base.email,
      website: base.website,
      company_size: base.companySize,
      staff: base.staff,
      registration_date: asIsoDate(registration.registrationDate),
      years_from_registration: registration.yearsFromRegistration,
      status: status.status,
      status_reason: status.reasonName,
      status_date: asIsoDate(status.date),
      share_capital: asNumber(founders.shareCapital),
      branches_count: branches.branchesCount,
      raw_report_json: {},
    }),
    structure_items: buildStructureItems(report, reportId, inn),
    financial_reports: buildFinancialReports(report, reportId, inn),
    risk_factors: buildRiskFactors(report, reportId, inn),
    arbitration: buildArbitration(report, reportId, inn),
    legal_events: buildLegalEvents(report, reportId, inn),
    procurements: buildProcurements(report, reportId, inn),
  };
}

temporary.drop();
const batch = [];
source.find({}).forEach((root) => batch.push(buildCard(root)));

if (batch.length) temporary.insertMany(batch, { ordered: true });

const sourceCount = source.countDocuments({});
const readCount = temporary.countDocuments({});
if (readCount !== sourceCount) {
  throw new Error("Read model count " + readCount + " differs from source count " + sourceCount);
}

temporary.renameCollection(readCollectionName, true);
print(
  "Built " + readCount + " application-ready cards in " +
  databaseName + "." + readCollectionName,
);
