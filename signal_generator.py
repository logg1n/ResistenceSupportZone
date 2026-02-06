import pandas as pd


class SignalGenerator:
    @staticmethod
    def check_engulfing(df: pd.DataFrame):
        """
        Логика поглощения:
        Тело текущей свечи должно полностью перекрывать тело предыдущей.
        """
        if len(df) < 2:
            return None

        prev = df.iloc[-2]  # Предыдущая свеча
        curr = df.iloc[-1]  # Текущая (только что закрытая)

        # Параметры тел (Open-Close)
        prev_body = prev["c"] - prev["o"]
        curr_body = curr["c"] - curr["o"]

        # BULLISH ENGULFING (Бычье поглощение)
        # 1. Предыдущая свеча красная, текущая зеленая
        # 2. Текущее тело больше предыдущего
        # 3. Закрытие выше открытия предыдущей, открытие ниже закрытия предыдущей
        if prev_body < 0 and curr_body > 0:
            if curr["c"] > prev["o"] and curr["o"] < prev["c"]:
                return "BUY"

        # BEARISH ENGULFING (Медвежье поглощение)
        # 1. Предыдущая свеча зеленая, текущая красная
        if prev_body > 0 and curr_body < 0:
            if curr["c"] < prev["o"] and curr["o"] > prev["c"]:
                return "SELL"

        return None
