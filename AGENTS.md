#　リポジトリの説明

研究用のコードを管理するリポジトリです。

## 研究の内容

ヒートシンクを最適化するためのコーどを作成しています。ヒートシンクをパラメトリックに設計し、Ansys Fluentを使用してシミュレーションを行い、ModeFrontierを使用して最適化を行います。

## 使用するソフトウェア

使用するソフトウェアは大きく分けて3つあります。

- Ansys Fluent
- grasshopper(Rhino8)
- ModeFrontier

## 実験の流れ

0. grasshopperを使用してヒートシンクのパラメトリックな設計を行います。(実装済み)
1. ModeFrontierを用いてヒートシンクのパラメータを生成します。
2. 生成されたパラメーとを使用し、grasshopperでヒートシンクのSTPファイルを生成します。
3. 生成されたSTPファイルをAnsys Fluentにインポートし、シミュレーションを行います。
4. シミュレーションの結果をModeFrontierにフィードバックし、最適化を行います。

## Ansys Fluentのシミュレーションコード

[pyFluent](https://github.com/ansys/pyfluent)を使用してAnsys Fluentのシミュレーションをするコードを作成しています。

### Ansys Fluentのシミュレーションコードの要件

- Ansys Fluentは2025R2を使用しています。そのため、それに即したコードを作成してください。
- pyFluentのドキュメントを参考にしてください。[pyFluent docs](https://fluent.docs.pyansys.com/version/0.38)
- API検索は以下のページを参考にすると方法が書いてあります。[pyFluent usability](https://fluent.docs.pyansys.com/version/0.38/user_guide/usability.html)
- コードはPythonで書いてください。
- コードはシンプルでわかりやすいものにしてください。
- コードには適切なコメントを入れてください。

## grasshopperのコード

grasshopperのコードは最終的な生成物に対してPython Scriptを使用してSTPファイルを生成するコードを作成しています。
