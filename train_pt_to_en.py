import gc
from torchtext.data import Dataset
from tqdm import tqdm

from playground import *
from os.path import join
from socket import gethostname
from util import get_timestamp, gpu_mem_restore
from nltk.translate.bleu_score import sentence_bleu as nltk_sentence_bleu
from sacrebleu import corpus_bleu as sacrebleu_corpus_bleu

BOS_WORD = '<s>'
EOS_WORD = '</s>'
BLANK_WORD = "<blank>"
PATH_TO_DATA = ".data/pt-to-en/data"
REF_FILE = os.path.join(PATH_TO_DATA, "val/text.en")


class PT_TO_EN_dataset(Dataset):
    """The PT-to-END translation task"""

    def __init__(self, path, fields, srcfile="text.pt", trgfile="text.en", **kwargs):
        if not isinstance(fields[0], (tuple, list)):
            fields = [('src', fields[0]), ('trg', fields[1])]
        src_path = join(path, srcfile)
        trg_path = join(path, trgfile)
        examples = []
        with open(src_path, mode='r', encoding='utf-8') as src_file, \
                open(trg_path, mode='r', encoding='utf-8') as trg_file:
            for src_line, trg_line in zip(src_file, trg_file):
                src_line, trg_line = src_line.strip(), trg_line.strip()
                if src_line != '' and trg_line != '':
                    examples.append(data.Example.fromlist(
                        [src_line, trg_line], fields))

        super(PT_TO_EN_dataset, self).__init__(examples, fields, **kwargs)

    @classmethod
    def splits(cls, path, fields, train='train', validation='val', test='dev5', **kwargs):
        """Create dataset objects for splits of the IWSLT dataset.

        Arguments:
            fields: A tuple containing the fields that will be used for data
                in each language.
        """

        train_path = join(path, train)
        validation_path = join(path, validation)
        test_path = join(path, test)

        train_data = cls(train_path, fields, **kwargs)
        val_data = cls(validation_path, fields, **kwargs)
        test_data = cls(test_path, fields, **kwargs)
        return tuple(d for d in (train_data, val_data, test_data))


def get_BLEU_nltk(data_iter, model, src_vocab, tgt_vocab, total_batches, fname="translation", **kwargs):
    def to_tokenized_text(tensor: torch.Tensor):
        strs = []
        for example_idx in range(tensor.shape[0]):
            s = []
            for i in tensor[example_idx]:
                token = tgt_vocab.itos[i]
                if token == BOS_WORD:
                    continue
                if token == EOS_WORD:
                    break
                s.append(token)
                assert token != BLANK_WORD
            strs.append(s)
        return strs

    bleu_acc = 0
    N = 0
    pbar = tqdm(total=total_batches)
    for i, batch in enumerate(data_iter):
        # Debug
        # print("-" * 10 + "SRC" + "-" * 10)
        # print("\n".join(totext(batch.src, src_vocab)))
        # print("-" * 10 + "TGT" + "-" * 10)
        # print("\n".join(totext(batch.trg, tgt_vocab)))
        # print("-" * 30)

        decoded = greedy_decode(model, batch.src, batch.src_mask, **kwargs)

        # Debug
        # decoded_text = totext(decoded, tgt_vocab)
        # get rid of special tokens
        # tmp = []
        # for s in decoded_text:
        #    idx = s.find("</s>")
        #    tmp.append(s[:idx] if idx > 0 else s)
        # decoded_text = tmp
        # print("-" * 10 + "DEC" + "-" * 10)
        # print("\n".join(decoded_text))
        # print("-" * 30)

        candidate_tokens = to_tokenized_text(decoded)
        ref_tokens = to_tokenized_text(batch.trg)
        assert len(candidate_tokens) == len(ref_tokens)

        # Debug
        # print("-" * 10 + "GT" + "-" * 10)
        # for ref in ref_tokens: print(ref)
        # print("-" * 30)

        # print("-" * 10 + "PREDICTION" + "-" * 10)
        # for c in candidate_tokens: print(c)
        # print("-" * 30)

        for k in range(len(candidate_tokens)):
            weights = (0.25, 0.25, 0.25, 0.25)
            # usually BLEU 1 to 4 is averaged, but this is problem if the sequence is too short
            # if len(candidate_tokens[k]) < 4:
            #   weights = (1 / len(candidate_tokens[k]) for _ in range(len(candidate_tokens[k])))\

            # auto_reweigh parameter should actually do t he same as if calling above 2 lines!
            sent_bleu = nltk_sentence_bleu([ref_tokens[k]], candidate_tokens[k], weights,
                                           auto_reweigh=True)

            bleu_acc += sent_bleu
            N += 1
        pbar.set_description(f"BLEU: {bleu_acc / N:.2f}")
        pbar.update(1)

    return bleu_acc / N


def get_BLEU_sacreBLEU(data_iter, model, src_vocab, tgt_vocab, total_batches, rfname="source", tfname="translation",
                       **kwargs):
    flag = model.training
    model.eval()
    pbar = tqdm(total=total_batches)
    hypotheses = "outputs/translation_pcfajcik_2019-04-10_17:57"
    references = "outputs/source_pcfajcik_2019-04-10_17:57"
    #references = f"outputs/{rfname}_{gethostname()}_{get_timestamp()}"
    #hypotheses = f"outputs/{tfname}_{gethostname()}_{get_timestamp()}"


    # with open(hypotheses, mode="w") as hf:
    #     with open(references, mode="w") as rf:
    #         for i, batch in enumerate(data_iter):
    #             # Debug
    #             # print("-" * 10 + "SRC" + "-" * 10)
    #             # print("\n".join(totext(batch.src, src_vocab)))
    #             # print("-" * 10 + "TGT" + "-" * 10)
    #             # print("\n".join(totext(batch.trg, tgt_vocab)))
    #             # print("-" * 30)
    #             ground_truth = totext(batch.trg, tgt_vocab)
    #             decoded = greedy_decode(model, batch.src, batch.src_mask, **kwargs)
    #             decoded_text = totext(decoded, tgt_vocab)
    #             # get rid of special tokens
    #             clean_decoded_text = []
    #             for s in decoded_text:
    #                 idx = s.find("</s>")
    #                 clean_decoded_text.append(s[:idx] if idx > 0 else s)
    #
    #             clean_ground_truth_text = []
    #             for s in ground_truth:
    #                 idx = s.find("</s>")
    #                 clean_ground_truth_text.append(s[1:idx] if idx > 0 else s[1:])
    #
    #             if not len(clean_decoded_text) == batch.src.shape[0]:
    #                 print(len(clean_decoded_text))
    #                 print(batch.src.shape[0])
    #
    #                 print(clean_decoded_text)
    #                 print(batch.src)
    #
    #             assert len(clean_decoded_text) == len(clean_ground_truth_text) == batch.src.shape[0]
    #             hf.write("\n".join(clean_decoded_text) + "\n")
    #             rf.write("\n".join(clean_ground_truth_text) + "\n")
    #             pbar.update(1)
    if flag:
        model.train()
    with open(hypotheses) as hypf:
        with open(references) as reff:
            return sacrebleu_corpus_bleu(hypf.read().split("\n")[:-1], [reff.read().split("\n")[:-1]])


@gpu_mem_restore
def get_BLEU(*args, method="sacreBLEU", **kwargs):
    if method == "nltk":
        return get_BLEU_nltk(*args, **kwargs)
    elif method == "sacreBLEU":
        return get_BLEU_sacreBLEU(*args, **kwargs)
    else:
        raise NotImplementedError(f"Unknown BLEU evaluation method {method}")


def train_PT_to_EN():
    """
    Train on  Portuguese-English Translation task
    """

    spacy_en = spacy.load('en')
    spacy_pt = spacy.load('pt')

    def tokenize_pt(text):
        # return str.split(text)
        return [tok.text for tok in spacy_pt.tokenizer(text)]

    def tokenize_en(text):
        # return str.split(text)
        return [tok.text for tok in spacy_en.tokenizer(text)]

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    SRC = data.Field(tokenize=tokenize_pt, pad_token=BLANK_WORD)
    TGT = data.Field(tokenize=tokenize_en, init_token=BOS_WORD,
                     eos_token=EOS_WORD, pad_token=BLANK_WORD)
    MAX_LEN = 512
    MAX_LEN_BLEU = 100
    train, val, test = PT_TO_EN_dataset.splits(path=PATH_TO_DATA, fields=(SRC, TGT),
                                               # use only examples shorter than 512
                                               filter_pred=lambda x: len(vars(x)['src']) <= MAX_LEN and
                                                                     len(vars(x)['trg']) <= MAX_LEN)
    # BEWARE OF THIS!
    # FIXME: Do not calculate bleu to original file -- it may contain sentences longer then max len

    MIN_FREQ = 2
    SRC.build_vocab(train.src, min_freq=MIN_FREQ)
    TGT.build_vocab(train.trg, min_freq=MIN_FREQ)

    pad_idx = TGT.vocab.stoi["<blank>"]

    criterion = LabelSmoothing(vocab_size=len(TGT.vocab), padding_idx=pad_idx, smoothing=0.1)
    TRAIN_BS = 1024 + 256 + 128
    VAL_BS = 1024 + 256
    BLEU_BS = 512
    # These examples are shuffled
    train_iter = DataIterator(train, batch_size=TRAIN_BS, device=device,
                              repeat=False, sort_key=lambda x: (len(x.src), len(x.trg)),
                              batch_size_fn=batch_size_fn, train=True)
    # These examples are not shuffled
    valid_iter = DataIterator(val, batch_size=VAL_BS, device=device,
                              repeat=False, sort_key=lambda x: (len(x.src), len(x.trg)),
                              batch_size_fn=batch_size_fn, train=False)
    BLEU_iter = DataIterator(val, batch_size=BLEU_BS, device=device,
                             repeat=False, sort_key=lambda x: (len(x.src), len(x.trg)),
                             batch_size_fn=batch_size_fn, train=False)
    bleu_batches = len([x for x in BLEU_iter])
    # model = create_transformer_model(len(SRC.vocab), len(TGT.vocab), N=6).to(device)
    model = torch.load(open("saved/"
                            "pt_to_en_E12_BLEU_0.3608543580919268_<class 'playground.EncoderDecoder'>L_1.5111518934411912_2019-04-10_17:15_pcknot3.pt",
                            "rb"),
                       map_location=device)
    model_opt = NoamOpt(model.src_embed[0].d_model, 1, 2000,
                        torch.optim.Adam(model.parameters(), lr=0, betas=(0.9, 0.98), eps=1e-9))
    for epoch in range(100):
        model.train()
        train_loss = val_loss = 0
        # train_loss = run_epoch((rebatch(pad_idx, b) for b in train_iter),
        #                       model,
        #                       SingleGPULossCompute(model.generator, criterion, model_opt))
        model.eval()
        # val_loss = run_epoch((rebatch(pad_idx, b) for b in valid_iter),
        #                      model,
        #                      SingleGPULossCompute(model.generator, criterion, opt=None))

        # This may be memory exhaustive

        bleu = -1
        if epoch > -1:
            bleu = get_BLEU((rebatch(pad_idx, b) for b in BLEU_iter), model, src_vocab=SRC.vocab,
                            tgt_vocab=TGT.vocab,
                            max_len=MAX_LEN_BLEU,
                            start_symbol=TGT.vocab.stoi["<s>"], total_batches=bleu_batches)

        logging.info(f"Train Loss: {train_loss}")
        logging.info(f"Validation Loss: {val_loss}")
        model.to(torch.device("cpu"))
        torch.save(model,
                   f"saved/pt_to_en_E{epoch}_BLEU_{bleu.score}_{str(model.__class__)}"
                   f"L_{val_loss}_{get_timestamp()}_{gethostname()}.pt")
        model.to(device)
        logging.info("-------------")
        logging.info(f"BLEU: {bleu}")
        logging.info("-------------")

# score=34.96939944413386,
# counts=[29569, 18255, 12013, 8006],
# totals=[43110, 41088, 39066, 37071],
# precisions=[68.58965437253538, 44.42903037383178, 30.750524752982134, 21.596396104771923],
# bp=0.9271464880101749,
# sys_len=43110,
# ref_len=46371
if __name__ == "__main__":
    setup_logging(os.path.basename(sys.argv[0]).split(".")[0],
                  logpath="logs/",
                  config_path="configurations/logging.yml")
    train_PT_to_EN()
