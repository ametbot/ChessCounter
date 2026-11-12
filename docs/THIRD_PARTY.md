# Сторонние компоненты

Python-зависимости перечислены в `source/requirements.txt` и устанавливаются отдельно. Их исходники и бинарные библиотеки не включены в этот репозиторий; каждая зависимость распространяется на своих условиях.

## OCR-модели

В `source/models/` включены две ONNX-модели PaddleOCR в представлении RapidOCR. Правообладатели исходных весов — Baidu и/или соответствующие правообладатели PaddleOCR; компоненты преобразования — авторы RapidOCR.

Согласно [описанию лицензирования моделей RapidOCR](https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/), модели из реестра RapidOCR распространяются под Apache-2.0. Копия [лицензии Apache-2.0](licenses/Apache-2.0.txt) включена в репозиторий. Это не лицензия собственного кода Chest Counter.

Хеши локальных файлов проверены по реестру `default_models.yaml` установленного RapidOCR 3.10.0. Файлы моделей в Chest Counter не изменены.

| Модель | SHA-256 | Источник из реестра |
| --- | --- | --- |
| `ch_PP-OCRv4_det_mobile.onnx` | `d2a7720d45a54257208b1e13e36a8479894cb74155a5efe29462512d42f49da9` | [RapidAI / ModelScope](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv4/det/ch_PP-OCRv4_det_mobile.onnx) |
| `cyrillic_PP-OCRv5_rec_mobile.onnx` | `90f761b4bfcce0c8c561c0cb5c887b0971d3ec01c32164bdf7374a35b0982711` | [RapidAI / ModelScope](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv5/rec/cyrillic_PP-OCRv5_rec_mobile.onnx) |

Upstream: [RapidOCR](https://github.com/RapidAI/RapidOCR), [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR), [лицензия PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE).

## Изображения

`source/assets/logo.png` и `logo.ico` — предоставленный для проекта логотип с игровыми элементами. `source/fixtures/chest_xp.png` — небольшой фрагмент игрового уведомления для OCR-теста. Эти изображения не объявляются частью лицензии Apache-2.0. Названия и игровые элементы Fortnite принадлежат соответствующим правообладателям.

`docs/images/interface.png` — превью приложения с тестовым значением 83; личные настройки и полный игровой скриншот в репозиторий не включены.
