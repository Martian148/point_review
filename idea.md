和市面上只是重复复习单词不通的是，point-review 核心点是在与 point，point 可以是一个单词或者一个词组，通过 AI 来出题帮忙快速回忆

### 关于 Point

#### Point 概念

Point 是这个项目的核心概念，Point 可以是一个 单词，可以是一个词组

Point 有一个标题，然后下面有若干释义/理解说明

例如：

```
- be accustomed to doing sth.
	- 习惯于做某事
	- I am accustomed to getting up early every morning. 我习惯每天早起
```

这个里面，`be accustomed to doing sth` 就是标题，后面的两条就是释义

又比如：

```
- perspective
	- n. 观点，看法，视角
		- from a different perspective = 从不同角度看
	- keep sth in perspective = 客观看待某事
```

在这个例子里面，`perspective` 是标题，剩下的就是释义，这也就说明了释义可以嵌套，像 markdown 的无序标题那样可以多层，比如一级释义下是意思，二级释义下是对这个例子的解释

#### Point 熟练度

Point 熟练度算法比较复杂，对于外部来说，我们使用五个星级等级来展示

```
⭐⭐⭐⭐⭐
```

但是内部另外保存数据结构：

```
mastery
last_reviewed_at
next_review_at
review_count
correct_count
wrong_count
correct_streak
```

新添加的 Point 设定为：未评估

在第一次复习后可以确定熟练度

#### Point 管理

在管理界面，可以对 Point 进行管理，也就是添加、删除、修改、查找

### AI 问答

在 AI 问答界面，使用 AI 生成一组问题，通常是 10 个，然后下方有A，B，C，D提供选择，AI 根据 
$$
\boxed{ \text{到期程度} + \text{薄弱程度} + \text{近期错误} + \text{新 Point} }
$$
来自动生成问题

#### 问题的形式

##### 直接语境释义

这是最基础、最高频的。

用 Point 中的单词/短语生成一句考研难度的长难句，然后问 “文中的 Point” 最接近什么意思

主要用于：单词/固定词组/熟词辟义

例如：

```
- impart
	- 传授；告知
```

问题
```
Universities are expected not merely to impart specialized knowledge but also to equip students with the ability to question accepted assumptions.
impart 在句中的含义是？
A...
B...
C...
D...
```

然后等着我去选

##### 根据整个句子理解 Point

难度再高一点，不直接问中文释义，而是问：作者使用这个表达实际上想说明什么？

```
The disappointing result should nevertheless be kept in perspective, given that the experiment was conducted under unusually restrictive conditions.

作者使用 kept in perspective 意在强调：
A...
B...
C...
D...
```

核心规则就是，单词的释义不是孤立的，而是在不同的语境中而不断变化的

