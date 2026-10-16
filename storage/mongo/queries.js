// SentinelLake - MongoDB walkthrough (query language, CRUD, arrays, aggregation, cursors, indexes)
// Run: docker compose exec mongo mongosh --quiet /opt/sentinellake/storage/mongo/queries.js
db = db.getSiblingDB("sentinel");
const show = (title, x) => { print(`\n== ${title}`); printjson(x); };

// READ - find with a filter, projection, sort, skip and limit
show("open incidents, newest first",
  db.incidents.find({ status: "open" }, { service: 1, endpoint: 1, type: 1, reason: 1 })
    .sort({ opened_at: -1 }).limit(5).toArray());

show("page 2 of all incidents (skip/limit pagination)",
  db.incidents.find({}, { service: 1, type: 1 }).sort({ opened_at: -1 }).skip(5).limit(5).toArray());

// COUNT
show("critical incident count", db.incidents.countDocuments({ severity: "critical" }));

// ARRAYS - every incident carries a timeline array of {at, action}
show("incidents that were updated at least 5 times",
  db.incidents.find({ "timeline.4": { $exists: true } }, { service: 1, type: 1, windows: 1 }).toArray());
show("incidents whose timeline contains a 'resolved' event",
  db.incidents.countDocuments({ timeline: { $elemMatch: { action: "resolved" } } }));

// AGGREGATION PIPELINE - incidents and mean time to resolve, per service
show("MTTR by service", db.incidents.aggregate([
  { $match: { status: "resolved" } },
  { $project: { service: 1, type: 1,
                minutes: { $divide: [{ $subtract: ["$resolved_at", "$opened_at"] }, 60000] } } },
  { $group: { _id: "$service", incidents: { $sum: 1 }, mttr_min: { $avg: "$minutes" },
              types: { $addToSet: "$type" } } },
  { $sort: { incidents: -1 } },
]).toArray());

// CURSOR - iterate without loading everything into memory
print("\n== cursor walk");
const cur = db.incidents.find({}, { service: 1, type: 1, severity: 1 }).sort({ opened_at: 1 });
while (cur.hasNext()) {
  const d = cur.next();
  print(`${d.severity.padEnd(8)} ${d.type.padEnd(14)} ${d.service}`);
}

// INDEX - confirm the query uses an index (IXSCAN) rather than scanning every document (COLLSCAN)
const plan = db.incidents.find({ status: "open" }).sort({ opened_at: -1 }).explain("queryPlanner");
show("winning plan stage", plan.queryPlanner.winningPlan.inputStage || plan.queryPlanner.winningPlan);
show("indexes", db.incidents.getIndexes().map(i => i.name));

// CREATE / UPDATE / DELETE - acknowledging an incident by hand
const id = "manual-demo-1";
db.incidents.insertOne({ _id: id, service: "orders", endpoint: "GET /v1/orders", type: "LATENCY_SPIKE",
  severity: "warning", status: "open", opened_at: new Date(), reason: "manual test" });
db.incidents.updateOne({ _id: id }, { $set: { acknowledged_by: "anushka" },
  $push: { timeline: { at: new Date(), action: "acknowledged" } } });
show("after update", db.incidents.findOne({ _id: id }));
db.incidents.deleteOne({ _id: id });

// MAP-REDUCE - the same idea as Hadoop's, inside the database.
// Deprecated since MongoDB 5.0 (the aggregation pipeline is faster) but still available.
show("incidents per type via mapReduce", db.incidents.mapReduce(
  function () { emit(this.type, 1); },                 // map
  function (key, values) { return Array.sum(values); }, // reduce
  { out: { inline: 1 } }
));
show("same result via aggregation",
  db.incidents.aggregate([{ $group: { _id: "$type", n: { $sum: 1 } } }]).toArray());

// EXPORT / IMPORT are command-line tools:
//   mongoexport --db sentinel --collection incidents --jsonArray --out /tmp/incidents.json
//   mongoimport --db sentinel --collection incidents_copy --jsonArray --file /tmp/incidents.json
