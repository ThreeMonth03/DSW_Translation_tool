# Translation

- UUID: `70442fd3-bea2-4e97-81f5-e9b33eec6cac`
- Event Type: `EditAnswerEvent`
- Edit only the `Translation (zh_Hant)` blocks below.

## label

> Shared field: edit this translation in `shared_blocks.md`.

### Source (en)

~~~text
Intermediate data
~~~

### Translation (zh_Hant)

~~~text

~~~

## advice

### Source (en)

~~~text
If the intermediate data is larger than either input or output data, you may consider minimizing the time it is stored. Make the balance between the CPU time needed if you need to re-calculate it versus the storage requirements. Sometimes it is possible to avoid storage at all by immediately running the whole analysis work flow.

It may also be useful to consider storing the intermediate data on a separate data volume from the rest of the project storage, which may not be backed up. This can not only reduce the storage costs, but also if the backup needs to be used it is better if it strictly contains the data that is needed for a restore, otherwise a restore i case of a problem may take much longer than strictly necessary.
~~~

### Translation (zh_Hant)

~~~text

~~~
