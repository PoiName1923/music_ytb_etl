const databases = JSON.parse(process.env.MONGO_INITDB_DATABASES);

databases.forEach(({ db: dbName, collections }) => {
    const database = db.getSiblingDB(dbName);
    collections.forEach((col) => {
        if (!database.getCollectionNames().includes(col)) {
            database.createCollection(col);
            print(`Created collection '${col}' in database '${dbName}'`);
        }
    });
});
