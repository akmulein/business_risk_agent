const databaseName = process.env.MONGO_DATABASE || "counterparties";
const collectionName = process.env.MONGO_COLLECTION || "reports";
const readCollectionName = process.env.MONGO_READ_COLLECTION || "counterparty_cards";
const reports = db.getSiblingDB(databaseName).getCollection(collectionName);
const cards = db.getSiblingDB(databaseName).getCollection(readCollectionName);

reports.createIndex(
  { "report.baseInfo.inn": 1, "report.reportDate": -1 },
  { name: "idx_inn_report_date", unique: true },
);

cards.createIndex(
  { "company_reports.inn": 1, "company_reports.report_date": -1 },
  { name: "idx_card_inn_report_date", unique: true },
);

reports.createIndex(
  { "report.baseInfo.riskLevel": 1 },
  { name: "idx_risk_level" },
);

reports.createIndex(
  { "report.status.status": 1 },
  { name: "idx_company_status" },
);

reports.createIndex(
  { "report.kindsOfActivityInfo.mainKindOfActivity.code": 1 },
  { name: "idx_primary_okved" },
);

reports.createIndex(
  { "report.relatedCompanies.inn": 1 },
  { name: "idx_related_company_inn" },
);

reports.createIndex(
  { "report.foundersInfo.cofounders.inn": 1 },
  { name: "idx_founder_inn" },
);

reports.createIndex(
  { "report.foundersInfo.authPerson.inn": 1 },
  { name: "idx_authorized_person_inn" },
);
