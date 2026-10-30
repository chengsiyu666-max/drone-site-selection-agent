# 真实数据上传契约与注意事项

## 支持的文件格式
- 支持 CSV（.csv）和 Excel（.xlsx、.xls、.xlsm），三种表都按第一张工作表读取。
- 列顺序不影响结果，多余的列会被自动忽略，不会报错。
- 至少需要上传起降点表；机坪表缺失时会回退到内置样例机坪，并与所选城市可能不符。

## 起降点表（stores）必需列
- pad_id（也可用 id 代替）、lat、lon 为必需列。
- 需求量列：优先读 rf_sales_10k，没有则读 annual_sales_10k；两列都缺时需求按 0 处理，选址结果不可用。
- 可选列：name、city、area_sqm（默认 100 平方米）、is_existing、initial_investment_10k、annual_fixed_cost_10k。

## 机坪表（rdcs）必需列
- vertiport_id（也可用 id 代替）、lat、lon 为必需列。
- altitude_limit_m（净空高度，米）强烈建议提供：缺列或缺失值会按 0 处理，随后被「净空小于 3 米剔除」硬约束全部过滤，导致没有任何选址结果。
- 可选列：name、city、is_no_fly_zone、max_flight_radius_km（默认 15 公里）、area_sqm、rent_per_sqm_day。

## 距离矩阵（distances）可选列
- 距离矩阵需要 vertiport_id、pad_id、distance_km 三列；不提供距离矩阵时引擎用球面距离（haversine）兜底，结果可用但精度略低。

## 城市列的处理
- 引擎按 city 列过滤数据；如果文件没有 city 列且上传时选择了城市，系统会自动补全该城市，并给出警告。
- 如果既没有 city 列、也没有选择城市，会直接报错提示补充。
- 如果 city 列的值与所选城市不一致，这些行会被全部过滤掉，最终得到空结果。

## 数据集的生命周期
- 上传并校验通过后，数据会注册为一个 dataset_id，之后调用选址工具时必须带上这个 dataset_id。
- 数据只保存在服务进程内存中，服务重启后注册表清空，需要重新上传。
- 上传失败会返回明确的中文原因，例如缺列、文件为空、格式不支持。
