## Usage
### Generate Markdown
```shell
python3 src/po_json_tree.py --po files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po --json files/dsw_root_2.7.0.json --out-dir output
```
### Generate Po
```shell
python3 src/md_to_po.py --en-md output/en.md --zh-md output/zh.md --original-po files/knowledge-models-common-dsw-knowledge-model-zh_Hant.po --out-po output/final_translated.po
```
### Check Output
```shell
python3 src/po_json_tree.py --po output/final_translated.po --json files/dsw_root_2.7.0.json --report-out output/final_report.json
```