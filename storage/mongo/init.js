// SentinelLake - MongoDB setup for the incidents collection.
// Mounted into /docker-entrypoint-initdb.d, so it runs on first start.
db = db.getSiblingDB("sentinel");

// A JSON-schema validator: Mongo is schema-flexible, but we still reject junk.
db.createCollection("incidents", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["service", "endpoint", "type", "severity", "status", "opened_at"],
      properties: {
        type: { enum: ["ERROR_BURST", "LATENCY_SPIKE", "LATENCY_DRIFT", "TRAFFIC_DROP"] },
        severity: { enum: ["warning", "critical"] },
        status: { enum: ["open", "resolved"] },
      },
    },
  },
});

// Indexes match the API's queries: "open incidents, newest first" and "history of one service".
db.incidents.createIndex({ status: 1, opened_at: -1 });
db.incidents.createIndex({ service: 1, opened_at: -1 });
db.incidents.createIndex({ type: 1 });
