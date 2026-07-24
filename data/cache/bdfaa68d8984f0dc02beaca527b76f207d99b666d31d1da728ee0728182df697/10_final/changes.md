# Changes Report

## Page 1, Sentence 14

**Original**

Recurrent neural networks, long short-term memory [13] and gated recurrent [7] neural networks in particular, have been firmly established as state of the art approaches in sequence modeling and transduction problems such as language modeling and machine translation [35, 2, 5].

**Corrected**

Recurrent neural networks, long short-term memory [13] and gated recurrent [7] neural networks in particular, have been firmly established as state-of-the-art approaches in sequence modeling and transduction problems such as language modeling and machine translation [35, 2, 5].

---

`state of the art` → `state-of-the-art`  
*hyphenation required for compound adjective* (Confidence: 0.95, Agreement Count: 2, Source Agents: languagetool, llm, Protected Reason: None)



## Page 1, Sentence 18

**Original**

Aligning the positions to steps in computation time, they generate a sequence of hidden states h t , as a function of the previous hidden state h t -1 and the input for position t .

**Corrected**

Aligning the positions to steps in computation time, they generate a sequence of hidden states h t, as a function of the previous hidden state h t -1 and the input for position t.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 36

**Original**

End-to-end memory networks are based on a recurrent attention mechanism instead of sequencealigned recurrence and have been shown to perform well on simple-language question answering and language modeling tasks

**Corrected**

End-to-end memory networks are based on a recurrent attention mechanism instead of sequence-aligned recurrence and have been shown to perform well on simple-language question answering and language modeling tasks

---

`sequencealigned` → `sequence-aligned`  
*The term should be hyphenated.* (Confidence: 0.80, Agreement Count: 1, Source Agents: languagetool, llm, Protected Reason: None)



## Page 1, Sentence 38

**Original**

To the best of our knowledge, however, the Transformer is the first transduction model relying entirely on self-attention to compute representations of its input and output without using sequencealigned RNNs or convolution.

**Corrected**

To the best of our knowledge, however, the Transformer is the first transduction model relying entirely on self-attention to compute representations of its input and output without using sequence aligned RNNs or convolution.

---

`sequencealigned` → `sequence aligned`  
*Possible spelling mistake found.* (Confidence: 0.78, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 43

**Original**

Here, the encoder maps an input sequence of symbol representations ( x 1 , ..., x n ) to a sequence of continuous representations z

**Corrected**

Here, the encoder maps an input sequence of symbol representations (x 1, ..., x n) to a sequence of continuous representations z

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 44

**Original**

= ( z 1 , ..., z n ) .

**Corrected**

= (z 1, ..., z n) .

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 45

**Original**

Given z , the decoder then generates an output sequence ( y 1 , ..., y m ) of symbols one element at a time.

**Corrected**

Given z, the decoder then generates an output sequence (y 1, ..., y m) of symbols one element at a time.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 54

**Original**

That is, the output of each sub-layer is LayerNorm( x +Sublayer( x )) , where Sublayer( x ) is the function implemented by the sub-layer itself.

**Corrected**

That is, the output of each sub-layer is LayerNorm(x +Sublayer(x)), where Sublayer(x) is the function implemented by the sub-layer itself.

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 55

**Original**

To facilitate these residual connections, all sub-layers in the model, as well as the embedding layers, produce outputs of dimension d model = 512 .

**Corrected**

To facilitate these residual connections, all sub-layers in the model, as well as the embedding layers, produce outputs of dimension d model = 512.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 60

**Original**

This masking, combined with fact that the output embeddings are offset by one position, ensures that the predictions for position i can depend only on the known outputs at positions less than i .

**Corrected**

This masking, combined with the fact that the output embeddings are offset by one position, ensures that the predictions for position i can depend only on the known outputs at positions less than i.

---

`fact` → `the fact`  
*Missing article before 'fact'* (Confidence: 0.80, Agreement Count: 1, Source Agents: llm, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 65

**Original**

of the values, where the weight assigned to each value

**Corrected**

Of the values, where the weight assigned to each value

---

`of` → `Of`  
*This sentence does not start with an uppercase letter.* (Confidence: 0.75, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 69

**Original**

The input consists of queries and keys of dimension d k , and values of dimension d v .

**Corrected**

The input consists of queries and keys of dimension d k, and values of dimension d v.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 70

**Original**

We compute the dot products of the query with all keys, divide each by √ d k , and apply a softmax function to obtain the weights on the values.

**Corrected**

We compute the dot products of the query with all keys, divide each by √ d k, and apply a softmax function to obtain the weights on the values.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 71

**Original**

In practice, we compute the attention function on a set of queries simultaneously, packed together into a matrix Q .

**Corrected**

In practice, we compute the attention function on a set of queries simultaneously, packed together into a matrix Q.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 72

**Original**

The keys and values are also packed together into matrices K and V .

**Corrected**

The keys and values are also packed together into matrices K and V.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 76

**Original**

Dot-product attention is identical to our algorithm, except for the scaling factor of 1 √ d k .

**Corrected**

Dot-product attention is identical to our algorithm, except for the scaling factor of 1 √ d k.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 81

**Original**

We suspect that for large values of d k , the dot products grow large in magnitude, pushing the softmax function into regions where it has extremely small gradients 4 .

**Corrected**

We suspect that for large values of d k, the dot products grow large in magnitude, pushing the softmax function into regions where it has tiny gradients 4.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`extremely small` → `tiny`  
*Consider using an extreme adjective for ‘small’.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 82

**Original**

To counteract this effect, we scale the dot products by 1 √ d k .

**Corrected**

To counteract this effect, we scale the dot products by 1 √ d k.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 84

**Original**

Instead of performing a single attention function with d model-dimensional keys, values and queries, we found it beneficial to linearly project the queries, keys and values h times with different, learned linear projections to d k ,

**Corrected**

Instead of performing a single attention function with d model-dimensional keys, values and queries, we found it beneficial to linearly project the queries, keys and values h times with different, learned linear projections to d k,

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 90

**Original**

Where the projections are parameter matrices W Q i ∈ R d model × d k , W i K ∈ R d model

**Corrected**

Where the projections are parameter matrices W Q i ∈ R d model × d k, W i K ∈ R d model

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 91

**Original**

× d k , W V i ∈ R d model × d v and W O ∈ R hd v × d model .

**Corrected**

× d k, W V i ∈ R d model × d v and W O ∈ R HD v × d model.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`hd` → `HD`  
*Possible spelling mistake found.* (Confidence: 0.78, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 95

**Original**

= 64 .

**Corrected**

= 64.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 103

**Original**

In a self-attention layer all of the keys, values and queries come from the same place, in this case, the output of the previous layer in the encoder.

**Corrected**

In a self-attention layer all the keys, values and queries come from the same place, in this case, the output of the previous layer in the encoder.

---

`all of the` → `all the`  
*Consider removing “of” to be more concise* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 107

**Original**

We implement this inside of scaled dot-product attention by masking out (setting to -∞ )

**Corrected**

We implement this inside of scaled dot-product attention by masking out (setting to -∞)

---

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 108

**Original**

all values in the input of the softmax which correspond to illegal connections.

**Corrected**

All values in the input of the softmax which correspond to illegal connections.

---

`all` → `All`  
*This sentence does not start with an uppercase letter.* (Confidence: 0.75, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 115

**Original**

The dimensionality of input and output is d model = 512 , and the inner-layer has dimensionality

**Corrected**

The dimensionality of input and output is d model = 512, and the inner-layer has dimensionality

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 116

**Original**

d ff = 2048 .

**Corrected**

d ff = 2048.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 128

**Original**

where pos is the position and i is the dimension.

**Corrected**

Where pos is the position and i is the dimension.

---

`where` → `Where`  
*This sentence does not start with an uppercase letter.* (Confidence: 0.75, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 130

**Original**

The wavelengths form a geometric progression from 2 π to 10000 · 2 π .

**Corrected**

The wavelengths form a geometric progression from 2 π to 10000 · 2 π.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 131

**Original**

We chose this function because we hypothesized it would allow the model to easily learn to attend by relative positions, since for any fixed offset k , PE pos + k can be represented as a linear function of PE pos .

**Corrected**

We chose this function because we hypothesized it would allow the model to easily learn to attend by relative positions, since for any fixed offset k, PE pos + k can be represented as a linear function of PE pos.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 135

**Original**

In this section we compare various aspects of self-attention layers to the recurrent and convolutional layers commonly used for mapping one variable-length sequence of symbol representations ( x 1 , ..., x n ) to another sequence of equal length ( z 1 , ..., z n ) , with x

**Corrected**

In this section we compare various aspects of self-attention layers to the recurrent and convolutional layers commonly used for mapping one variable-length sequence of symbol representations (x 1, ..., x n) to another sequence of equal length (z 1, ..., z n) , with x

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 136

**Original**

i , z i ∈ R d , such as a hidden layer in a typical sequence transduction encoder or decoder.

**Corrected**

i, z i ∈ R d, such as a hidden layer in a typical sequence transduction encoder or decoder.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 145

**Original**

As noted in Table 1, a self-attention layer connects all positions with a constant number of sequentially executed operations, whereas a recurrent layer requires O ( n ) sequential operations.

**Corrected**

As noted in Table 1, a self-attention layer connects all positions with a constant number of sequentially executed operations, whereas a recurrent layer requires O (n) sequential operations.

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 146

**Original**

In terms of computational complexity, self-attention layers are faster than recurrent layers when the sequence length n is smaller than the representation dimensionality d , which is most often the case with sentence representations used by state-of-the-art models in machine translations, such as word-piece [38] and byte-pair [31] representations.

**Corrected**

In terms of computational complexity, self-attention layers are faster than recurrent layers when the sequence length n is smaller than the representation dimensionality d, which is most often the case with sentence representations used by state-of-the-art models in machine translations, such as word-piece [38] and byte-pair [31] representations.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 148

**Original**

This would increase the maximum path length to O ( n/r ) .

**Corrected**

This would increase the maximum path length to O (n/r) .

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 151

**Original**

Doing so requires a stack of O ( n/k ) convolutional layers in the case of contiguous kernels, or O ( log k ( n )) in the case of dilated convolutions

**Corrected**

Doing so requires a stack of O (n/k) convolutional layers in the case of contiguous kernels, or O (log k (n)) in the case of dilated convolutions

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 153

**Original**

Convolutional layers are generally more expensive than recurrent layers, by a factor of k .

**Corrected**

Convolutional layers are generally more expensive than recurrent layers, by a factor of k.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 154

**Original**

Separable convolutions [6], however, decrease the complexity considerably, to O ( k · n · d + n

**Corrected**

Separable convolutions [6], however, decrease the complexity considerably, to O (k · n · d + n

---

`( ` → `(`  
*Don’t put a space after the opening parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 155

**Original**

· d 2 ) .

**Corrected**

· d 2) .

---

` )` → `)`  
*Don’t put a space before the closing parenthesis.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 156

**Original**

Even with k = n , however, the complexity of a separable convolution is equal to the combination of a self-attention layer and a point-wise feed-forward layer, the approach we take in our model.

**Corrected**

Even with k = n, however, the complexity of a separable convolution is equal to the combination of a self-attention layer and a point-wise feed-forward layer, the approach we take in our model.

---

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 157

**Original**

As side benefit, self-attention could yield more interpretable models.

**Corrected**

As a side benefit, self-attention could yield more interpretable models.

---

`As side benefit` → `As a side benefit`  
*Missing article 'a'* (Confidence: 0.80, Agreement Count: 1, Source Agents: llm, Protected Reason: None)



## Page 1, Sentence 164

**Original**

Sentences were encoded using byte-pair encoding [3], which has a shared sourcetarget vocabulary of about 37000 tokens.

**Corrected**

Sentences were encoded using byte-pair encoding [3], which has a shared source-target vocabulary of about 37000 tokens.

---

`sourcetarget` → `source-target`  
*The compound term should be hyphenated.* (Confidence: 0.80, Agreement Count: 1, Source Agents: languagetool, llm, Protected Reason: None)



## Page 1, Sentence 172

**Original**

For our big models,(described on the bottom line of table 3), step time was 1.0 seconds.

**Corrected**

For our big models, (described on the bottom line of table 3), step time was 1.0 seconds.

---

`,(` → `, (`  
*Put a space after the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 176

**Original**

[20] with β 1 = 0 . 9 , β 2 = 0 .

**Corrected**

[20] with β 1 = 0. 9, β 2 = 0.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 177

**Original**

98 and ε = 10 -9 .

**Corrected**

98 and ε = 10 -9.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 180

**Original**

We used warmup steps = 4000 .

**Corrected**

We used warmup steps = 4000.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 186

**Original**

For the base model, we use a rate of P drop = 0 . 1 .

**Corrected**

For the base model, we use a rate of P drop = 0. 1.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 187

**Original**

Label Smoothing During training, we employed label smoothing of value ε ls = 0 . 1

**Corrected**

Label Smoothing During training, we employed label smoothing of value ε_ls = 0. 1

---

`ε ls` → `ε_ls`  
*Variable names should not have spaces between characters.* (Confidence: 0.80, Agreement Count: 1, Source Agents: llm, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 192

**Original**

On the WMT 2014 English-to-German translation task, the big transformer model (Transformer (big) in Table 2) outperforms the best previously reported models (including ensembles) by more than 2 . 0

**Corrected**

On the WMT 2014 English-to-German translation task, the big transformer model (Transformer (big) in Table 2) outperforms the best previously reported models (including ensembles) by more than 2.0

---

`2 . 0` → `2.0`  
*Extra space before decimal point* (Confidence: 0.80, Agreement Count: 1, Source Agents: languagetool, llm, Protected Reason: None)



## Page 1, Sentence 193

**Original**

BLEU, establishing a new state-of-the-art BLEU score of 28 .

**Corrected**

BLEU, establishing a new state-of-the-art BLEU score of 28.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 194

**Original**

4 .

**Corrected**

4.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 196

**Original**

Training took 3 .

**Corrected**

Training took 3.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 199

**Original**

On the WMT 2014 English-to-French translation task, our big model achieves a BLEU score of 41 . 0 , outperforming all of the previously published single models, at less than 1 / 4 the training cost of the previous state-of-the-art model.

**Corrected**

On the WMT 2014 English-to-French translation task, our big model achieves a BLEU score of 41. 0, outperforming all the previously published single models, at less than 1 / 4 the training cost of the previous state-of-the-art model.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`all of the` → `all the`  
*Consider removing “of” to be more concise* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 200

**Original**

The Transformer (big) model trained for English-to-French used dropout rate P drop = 0 . 1 , instead of 0 . 3 .

**Corrected**

The Transformer (big) model trained for English-to-French used dropout rate P drop = 0. 1, instead of 0. 3.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` ,` → `,`  
*Put a space after the comma, but not before the comma.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 203

**Original**

We used beam search with a beam size of 4 and length penalty α = 0 . 6

**Corrected**

We used beam search with a beam size of 4 and length penalty α = 0.6

---

`α = 0 . 6` → `α = 0.6`  
*Extra space before the decimal point* (Confidence: 0.80, Agreement Count: 1, Source Agents: languagetool, llm, Protected Reason: None)



## Page 1, Sentence 206

**Original**

We set the maximum output length during inference to input length + 50 , but terminate early when possible [38].

**Corrected**

We set the maximum output length during inference to input length + 50, but terminate early when possible [38].

---

`input length + 50 ,` → `input length + 50,`  
*Space after the comma is unnecessary* (Confidence: 0.80, Agreement Count: 1, Source Agents: languagetool, llm, Protected Reason: None)



## Page 1, Sentence 228

**Original**

We performed only a small number of experiments to select the dropout, both attention and residual (section 5.4), learning rates and beam size on the Section 22 development set, all other parameters remained unchanged from the English-to-German base translation model.

**Corrected**

We performed only a few experiments to select the dropout, both attention and residual (section 5.4), learning rates and beam size on the section 22 development set, all other parameters remained unchanged from the English-to-German base translation model.

---

`a small number of` → `a few`  
*Specify a number, remove phrase, use “a few”, or use “some”* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)

`Section` → `section`  
*Inconsistent capitalization* (Confidence: 0.80, Agreement Count: 1, Source Agents: llm, Protected Reason: None)



## Page 1, Sentence 229

**Original**

During inference, we increased the maximum output length to input length + 300 .

**Corrected**

During inference, we increased the maximum output length to input length + 300.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 230

**Original**

We used a beam size of 21 and α = 0 . 3 for both WSJ only and the semi-supervised setting.

**Corrected**

We used a beam size of 21 and α = 0. 3 for both WSJ only and the semi-supervised setting.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 231

**Original**

Our results in Table 4 show that despite the lack of task-specific tuning our model performs surprisingly well, yielding better results than all previously reported models with the exception of the Recurrent Neural Network Grammar

**Corrected**

Our results in Table 4 show that despite the lack of task-specific tuning our model performs surprisingly well, yielding better results than all previously reported models except the Recurrent Neural Network Grammar

---

`with the exception of` → `except`  
*Consider using “except” or “except for”* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)



## Page 1, Sentence 243

**Original**

The code we used to train and evaluate our models is available at tensorflow/tensor2tensor .

**Corrected**

The code we used to train and evaluate our models is available at tensorflow/tensor2tensor.

---

` .` → `.`  
*Don’t put a space before the full stop.* (Confidence: 0.73, Agreement Count: 1, Source Agents: languagetool, Protected Reason: None)


