import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
import random
from itertools import combinations
import datetime
import asyncio

# --- 設定 ---
LOG_CHANNEL_ID = 1507680654106689657       # 既存のポーカー管理用ログチャンネル
RESULT_HISTORY_CHANNEL_ID = 1507717201619324968 # 👈 ユーザーがいつでも結果を見られるチャンネル
SUITS = ['♠️', '♥️', '♣️', '♦️']
SUIT_CHARS = {'♠️': 's', '♥️': 'h', '♣️': 'c', '♦️': 'd'}
CHAR_TO_SUIT = {'s': '♠️', 'h': '♥️', 'c': '♣️', 'd': '♦️'}
RANK_MAP = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':11,'Q':12,'K':13,'A':14}

# 🚫 現在卓を立てて募集・プレイ中のユーザーIDを記憶するリスト
ACTIVE_HOSTS = []

def evaluate_hand(cards):
    best_hand_score = (-1, "High Card", [0, 0, 0, 0, 0])
    for combo in combinations(cards, 5):
        sorted_cards = sorted(combo, key=lambda x: x['val'], reverse=True)
        values = [c['val'] for c in sorted_cards]
        suits = [c['suit'] for c in sorted_cards]
        
        is_flush = len(set(suits)) == 1
        is_straight = all(values[i] - values[i+1] == 1 for i in range(4))
        is_low_straight = (values == [14, 5, 4, 3, 2])
        
        if is_low_straight:
            is_straight = True
            values = [5, 4, 3, 2, 1]

        counts = {v: values.count(v) for v in set(values)}
        counts_list = sorted(counts.values(), reverse=True)
        unique_values = sorted(counts.keys(), key=lambda x: (counts[x], x), reverse=True)

        if is_straight and is_flush and values[0] == 14:
            score = (10, "Royal Flush", values)
        elif is_straight and is_flush:
            score = (9, "Straight Flush", values)
        elif counts_list == [4, 1]:
            score = (8, "Four of a Kind", unique_values)
        elif counts_list == [3, 2]:
            score = (7, "Full House", unique_values)
        elif is_flush:
            score = (6, "Flush", values)
        elif is_straight:
            score = (5, "Straight", values)
        elif counts_list == [3, 1, 1]:
            score = (4, "Three of a Kind", unique_values)
        elif counts_list == [2, 2, 1]:
            score = (3, "Two Pair", unique_values)
        elif counts_list == [2, 1, 1, 1]:
            score = (2, "One Pair", unique_values)
        else:
            score = (1, "High Card", values)

        if score[0] > best_hand_score[0]:
            best_hand_score = score
        elif score[0] == best_hand_score[0]:
            if score[2] > best_hand_score[2]:
                best_hand_score = score
                
    return best_hand_score

class PokerPlayer:
    def __init__(self, user):
        self.user = user
        self.hand = []
        self.is_folded = False
        self.is_all_in = False
        self.bet_in_phase = 0  
        self.total_bet = 0     

class PokerRaiseModal(discord.ui.Modal, title="レイズ額の入力"):
    amount_input = discord.ui.TextInput(label="レイズ後のトータルベット額を入力してください", placeholder="例: 500", min_length=1, max_length=10)

    def __init__(self, game_view, min_raise_total):
        super().__init__()
        self.view = game_view
        self.min_raise_total = min_raise_total
        self.amount_input.label = f"合計ベット額 (最低: {min_raise_total:,}枚)"

    async def on_submit(self, i: discord.Interaction):
        try:
            target_total = int(self.amount_input.value)
        except ValueError:
            return await i.response.send_message("❌ 有効な数字を入力してください。", ephemeral=True)

        player = self.view.players[self.view.current_turn_idx]
        if target_total < self.min_raise_total:
            return await i.response.send_message(f"❌ レイズ額が低すぎます。最低でも合計 {self.min_raise_total:,} 枚にする必要があります。", ephemeral=True)

        diff = target_total - player.bet_in_phase
        res = self.view.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
        current_coins = res.data[0].get('coin_count', 0) if res.data else 0

        if current_coins < diff:
            return await i.response.send_message(f"❌ コインが足りません。必要枚数: {diff:,}枚 (所持: {current_coins:,}枚)", ephemeral=True)

        self.view.bot.supabase.rpc('update_user_stats', {'u_id': str(i.user.id), 'coin_change': -diff}).execute()

        player.bet_in_phase += diff
        player.total_bet += diff
        self.view.pot += diff
        self.view.current_bet = player.bet_in_phase
        self.view.action_counter = 0 

        if current_coins == diff:
            player.is_all_in = True
            await i.channel.send(f"🔥 **{i.user.display_name} がオールイン！**")

        await self.view.next_turn(i)


class PokerGameView(View):
    def __init__(self, bot, creator, entry_bet):
        super().__init__(timeout=None)
        self.bot, self.creator, self.entry_bet = bot, creator, entry_bet
        if creator and hasattr(creator, 'bot') and creator.bot:
            self.players = []
            self.creator_id = 0
            self.creator_user = None
        else:
            self.players = [PokerPlayer(creator)] if creator else []
            self.creator_id = creator.id if creator else 0
            self.creator_user = creator
            
        self.pot = 0
        self.current_bet = 0
        self.phase = "WAITING" 
        self.current_turn_idx = 0
        self.community_cards = []
        self.deck = [{"suit": s, "rank": r, "val": v} for s in SUITS for r, v in RANK_MAP.items()]
        random.shuffle(self.deck)
        self.action_counter = 0
        self.message = None

        self.update_action_buttons()

    def create_main_embed(self):
        emb = discord.Embed(title=f"🃏 本格ポーカー (テキサスホールデム) - {self.phase}", color=0x2ecc71)
        
        cc_list = [f"{c['suit']}`{c['rank']}`" for c in self.community_cards]
        while len(cc_list) < 5:
            cc_list.append("🎴")
        cc_display = " ".join(cc_list)
        emb.add_field(name="🏛️ コミュニティカード (場)", value=f"### {cc_display}", inline=False)
        
        p_info = ""
        if not self.players:
            p_info = "*まだ参加者はいません。下のボタンから参加してください。*"
        else:
            for i, p in enumerate(self.players):
                mark = "▶️ " if (self.phase != "WAITING" and i == self.current_turn_idx) else "👤 "
                status = ""
                if p.is_folded: status = " *(FOLD)*"
                elif p.is_all_in: status = " **(ALL-IN)**"
                p_info += f"{mark}**{p.user.display_name}**: ベット {p.bet_in_phase:,}枚 / 総額 {p.total_bet:,}枚{status}\n"
            
        emb.add_field(name="👥 プレイヤー一覧", value=p_info, inline=True)
        emb.add_field(name="💰 ポット合計", value=f"## {self.pot:,} 枚", inline=True)
        
        if self.phase == "WAITING":
            emb.description = f"参加費: **{self.entry_bet:,}枚**\nプレイヤーが集まったら、**卓を立てた人**が「ゲーム開始」を押してください。"
        else:
            active_p = self.players[self.current_turn_idx]
            emb.description = f"現在のアクション順: {active_p.user.mention}\n現在のコールに必要な合計額: **{self.current_bet:,}枚**\n\n🤫 *参加者は下の「手札を確認する」から自分だけのカードを見られます！*"
        return emb

    def update_action_buttons(self):
        self.clear_items()
        
        if self.phase == "WAITING":
            self.add_item(Button(label="手札確認", style=discord.ButtonStyle.secondary, custom_id="pkr_init_peek", disabled=True, row=0))
            self.add_item(Button(label="参加する", style=discord.ButtonStyle.primary, custom_id=f"pkr_init_join_{self.creator_id}", row=0))
            self.add_item(Button(label="ゲーム開始", style=discord.ButtonStyle.danger, custom_id=f"pkr_init_start_{self.creator_id}", row=0))
        else:
            token_list = []
            for p in self.players:
                if p.hand and len(p.hand) == 2:
                    c1, c2 = p.hand[0], p.hand[1]
                    s1, r1 = SUIT_CHARS.get(c1['suit'], 's'), c1['rank']
                    s2, r2 = SUIT_CHARS.get(c2['suit'], 's'), c2['rank']
                    token_list.append(f"{p.user.id}-{s1}{r1}.{s2}{r2}")
            
            custom_id_with_hands = f"pkr_x_{'_'.join(token_list)}"
            if len(custom_id_with_hands) > 100:
                custom_id_with_hands = "pkr_in_game_peek"

            self.add_item(Button(label="👁️ 手札を確認する", style=discord.ButtonStyle.secondary, custom_id=custom_id_with_hands, row=0))
            
            player = self.players[self.current_turn_idx]
            if player.bet_in_phase == self.current_bet:
                self.add_item(PokerGameActionButton(label="チェック", style=discord.ButtonStyle.success, action_type="call", row=1))
            else:
                diff = self.current_bet - player.bet_in_phase
                self.add_item(PokerGameActionButton(label=f"コール (【追加】{diff:,}枚)", style=discord.ButtonStyle.primary, action_type="call", row=1))
            
            self.add_item(PokerGameActionButton(label="レイズ (自由入力)", style=discord.ButtonStyle.danger, action_type="raise", row=1))
            self.add_item(PokerGameActionButton(label="フォールド", style=discord.ButtonStyle.secondary, action_type="fold", row=1))

    async def send_game_log(self, log_embed):
        try:
            channel = self.bot.get_channel(LOG_CHANNEL_ID)
            if channel:
                await channel.send(embed=log_embed)
        except Exception as e:
            print(f"ポーカーログ送信中にエラーが発生しました: {e}")

    async def send_result_history(self, embed):
        """指定された公開用結果履歴チャンネルにリザルトを送信する (自動削除なし)"""
        try:
            channel = self.bot.get_channel(RESULT_HISTORY_CHANNEL_ID)
            if channel:
                await channel.send(embed=embed)
        except Exception as e:
            print(f"ユーザー用結果履歴送信中にエラーが発生しました: {e}")

    async def handle_global_join(self, i: discord.Interaction):
        if self.phase != "WAITING":
            return await i.response.send_message("❌ 既にゲームが開始されています。", ephemeral=True)
        if any(p.user.id == i.user.id for p in self.players):
            return await i.response.send_message("❌ 既に参加しています。", ephemeral=True)

        res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
        current_coins = res.data[0].get('coin_count', 0) if res.data else 0
        if current_coins < self.entry_bet:
            return await i.response.send_message(f"❌ 参加コインが足りません！必要: {self.entry_bet:,}枚 (所持: {current_coins:,}枚)", ephemeral=True)

        self.players.append(PokerPlayer(i.user))
        self.update_action_buttons()
        await i.response.edit_message(embed=self.create_main_embed(), view=self)

    async def handle_global_start(self, i: discord.Interaction):
        if i.user.id != self.creator_id:
            return await i.response.send_message("❌ この卓を開始できるのは、卓を立てた作成者（ホスト）のみです！", ephemeral=True)
            
        if len(self.players) < 2:
            return await i.response.send_message("❌ ポーカーを始めるには最低2人のプレイヤーが必要です。", ephemeral=True)
        if self.phase != "WAITING":
            return

        self.phase = "PRE-FLOP"
        for p in self.players:
            self.bot.supabase.rpc('update_user_stats', {'u_id': str(p.user.id), 'coin_change': -self.entry_bet}).execute()
            p.hand = [self.deck.pop(), self.deck.pop()]
            p.bet_in_phase = self.entry_bet
            p.total_bet = self.entry_bet
            self.pot += self.entry_bet
            
        self.current_bet = self.entry_bet
        self.current_turn_idx = 0
        self.action_counter = 0

        self.update_action_buttons()
        await i.response.edit_message(embed=self.create_main_embed(), view=self)

    async def next_turn(self, i: discord.Interaction):
        num_p = len(self.players)
        active_players = [p for p in self.players if not p.is_folded and not p.is_all_in]

        if len([p for p in self.players if not p.is_folded]) <= 1 or len(active_players) == 0:
            await self.showdown()
            return

        self.current_turn_idx = (self.current_turn_idx + 1) % num_p
        while self.players[self.current_turn_idx].is_folded or self.players[self.current_turn_idx].is_all_in:
            self.current_turn_idx = (self.current_turn_idx + 1) % num_p

        playing_p = [p for p in self.players if not p.is_folded]
        all_matched = all(p.is_all_in or p.bet_in_phase == self.current_bet for p in playing_p)

        if self.action_counter >= len(playing_p) and all_matched:
            await self.proceed_phase(i)
        else:
            self.update_action_buttons()
            if not i.is_expired():
                await i.response.edit_message(embed=self.create_main_embed(), view=self)
            else:
                await self.message.edit(embed=self.create_main_embed(), view=self)

    async def proceed_phase(self, i: discord.Interaction):
        self.action_counter = 0
        for p in self.players: 
            p.bet_in_phase = 0  
        self.current_bet = 0

        if self.phase == "PRE-FLOP":
            self.phase, self.community_cards = "FLOP", [self.deck.pop() for _ in range(3)]
        elif self.phase == "FLOP":
            self.phase = "TURN"; self.community_cards.append(self.deck.pop())
        elif self.phase == "TURN":
            self.phase = "RIVER"; self.community_cards.append(self.deck.pop())
        else:
            await self.showdown()
            return

        active_players = [p for p in self.players if not p.is_folded and not p.is_all_in]
        if len([p for p in self.players if not p.is_folded]) <= 1 or len(active_players) <= 1:
            while len(self.community_cards) < 5:
                self.community_cards.append(self.deck.pop())
            await self.showdown()
            return

        self.current_turn_idx = 0
        while self.players[self.current_turn_idx].is_folded or self.players[self.current_turn_idx].is_all_in:
            self.current_turn_idx = (self.current_turn_idx + 1) % len(self.players)

        self.update_action_buttons()
        await i.response.edit_message(embed=self.create_main_embed(), view=self)

    def calculate_side_pots(self):
        pots = []
        player_bets = {p: p.total_bet for p in self.players}
        
        while True:
            eligible_players = [p for p, bet in player_bets.items() if bet > 0 and not p.is_folded]
            if not eligible_players:
                break
                
            active_bets_with_value = [bet for p, bet in player_bets.items() if bet > 0]
            if not active_bets_with_value:
                break
            min_bet = min(active_bets_with_value)
            
            pot_amount = 0
            pot_contributors = []
            
            for p in self.players:
                if player_bets[p] >= min_bet:
                    pot_amount += min_bet
                    player_bets[p] -= min_bet
                    if not p.is_folded:
                        pot_contributors.append(p)
                elif player_bets[p] > 0:
                    pot_amount += player_bets[p]
                    player_bets[p] = 0
                    if not p.is_folded:
                        pot_contributors.append(p)
                        
            if pot_amount > 0:
                pots.append({"amount": pot_amount, "contributors": pot_contributors})
                
        return pots

    async def showdown(self):
        self.phase = "SHOWDOWN"
        
        if self.creator_id in ACTIVE_HOSTS:
            ACTIVE_HOSTS.remove(self.creator_id)

        emb = self.create_main_embed()
        active = [p for p in self.players if not p.is_folded]
        
        host_mention = f"<@{self.creator_id}>" if self.creator_id else "不明"
        participants_str = ", ".join([p.user.mention for p in self.players])

        log_emb = discord.Embed(title="📊 ポーカー試合ログ (サイドポット完全版)", color=0x3498db, timestamp=datetime.datetime.now())
        log_emb.add_field(name="👑 卓を立てた人", value=host_mention, inline=True)
        log_emb.add_field(name="👥 参加者", value=participants_str, inline=False)

        # 💡 1️⃣【フォールド勝ちの場合】
        if len(active) == 1:
            winner = active[0]
            self.bot.supabase.rpc('update_user_stats', {'u_id': str(winner.user.id), 'coin_change': self.pot}).execute()
            
            emb.title = "🏆 勝者決定 (フォールド勝ち)"
            desc = f"### 🎉 勝者: {winner.user.mention}\n他プレイヤーが全員降りたため、ポットの **{self.pot:,} 枚** を獲得しました！\n\n"
            
            w_hand_s = ' '.join([f"{c['suit']}`{c['rank']}`" for c in winner.hand]) if winner.hand else "❓❓"
            desc += f"**🤫 勝者の手札公開：**\n**{winner.user.display_name}** の手札は 【 {w_hand_s} 】 でした！\n\n"
            desc += "⏱️ *このメッセージは15秒後に自動削除されます。*"
            
            emb.description = desc
            await self.message.edit(embed=emb, view=None)

            # 管理用ログに送信
            log_emb.add_field(name="🏆 勝者", value=f"{winner.user.mention} (フォールド勝ち)", inline=True)
            log_emb.add_field(name="💰 獲得総額", value=f"{self.pot:,} 枚", inline=True)
            log_emb.add_field(name="🃏 勝者の手札", value=w_hand_s, inline=False)
            await self.send_game_log(log_emb)
            
            # 📢 ユーザー公開用結果履歴に送信 (消えないログ)
            public_emb = discord.Embed(title="🏆 ポーカー対戦結果 (フォールド勝ち)", color=0xf1c40f, timestamp=datetime.datetime.now())
            public_emb.description = f"**卓作成者:** {host_mention}\n**勝者:** {winner.user.mention}\n**獲得額:** {self.pot:,} 枚\n**勝者の手札:** {w_hand_s}"
            await self.send_result_history(public_emb)

            await asyncio.sleep(15)  # 👈 5秒から15秒に延長
            try: await self.message.delete()
            except: pass
            return

        # 💡 2️⃣【通常ショーダウン＆サイドポット計算】
        player_scores = {}
        for p in active:
            if not p.hand:
                p.hand = [{"suit": "❓", "rank": "❓", "val": 0}]
            player_scores[p] = evaluate_hand(p.hand + self.community_cards)

        calculated_pots = self.calculate_side_pots()
        
        emb.title = "🏆 結果発表 (ショーダウン)"
        desc = "### 💰 各ポットの獲得分配結果\n"
        winners_log_str = ""

        for idx, pot_data in enumerate(calculated_pots):
            pot_amt = pot_data["amount"]
            contributors = pot_data["contributors"]
            
            if not contributors:
                continue
                
            pot_name = "メインポット" if idx == 0 else f"サイドポット {idx}"
            contrib_scores = [(p, player_scores[p]) for p in contributors if p in player_scores]
            contrib_scores.sort(key=lambda x: (x[1][0], x[1][2]), reverse=True)
            
            best_rank_score = contrib_scores[0][1][0]
            best_kicker_list = contrib_scores[0][1][2]
            
            pot_winners = []
            for item in contrib_scores:
                p_rank = item[1][0]
                p_kickers = item[1][2]
                if p_rank == best_rank_score and p_kickers == best_kicker_list:
                    pot_winners.append(item)
            
            num_pot_winners = len(pot_winners)
            split_share = pot_amt // num_pot_winners
            
            if num_pot_winners > 1:
                desc += f"**💵 {pot_name} ({pot_amt:,}枚) ➡ 引き分け ({num_pot_winners}名)**\n"
                for w_p, w_res in pot_winners:
                    self.bot.supabase.rpc('update_user_stats', {'u_id': str(w_p.user.id), 'coin_change': split_share}).execute()
                    desc += f" 🏆 {w_p.user.mention} が **{split_share:,}枚** 獲得! ({w_res[1]})\n"
                    winners_log_str += f"• {pot_name}: {w_p.user.mention} (分当: {split_share:,}枚 / 役: {w_res[1]})\n"
            else:
                w_p, w_res = pot_winners[0]
                self.bot.supabase.rpc('update_user_stats', {'u_id': str(w_p.user.id), 'coin_change': pot_amt}).execute()
                desc += f"**💵 {pot_name} ({pot_amt:,}枚) ➡ 総取り**\n 🏆 {w_p.user.mention} が **{pot_amt:,}枚** 獲得! ({w_res[1]})\n"
                winners_log_str += f"• {pot_name}: {w_p.user.mention} (獲得: {pot_amt:,}枚 / 役: {w_res[1]})\n"

        desc += "\n**🃏 【全員の手札公開】**\n"
        hands_log_str = ""
        for p in self.players:
            h_s = ' '.join([f"{c['suit']}`{c['rank']}`" for c in p.hand]) if p.hand else "❓❓"
            
            if p.is_folded:
                desc += f"• ~~{p.user.display_name}~~: {h_s} *(FOLD)*\n"
                hands_log_str += f"• {p.user.display_name}: {h_s} (FOLD)\n"
            else:
                p_res = player_scores.get(p, (1, "High Card", [0,0,0,0,0]))
                desc += f"• **{p.user.display_name}**: {h_s} ➡ **{p_res[1]}**\n"
                hands_log_str += f"• {p.user.display_name}: {h_s} (役: {p_res[1]})\n"

        desc += "\n⏱️ *このメッセージは15秒後に自動削除されます。*"
        emb.description = desc
        await self.message.edit(embed=emb, view=None)

        # 管理用ログへの送信
        log_emb.add_field(name="🏆 勝者分配内訳", value=winners_log_str if winners_log_str else "なし", inline=False)
        log_emb.add_field(name="💰 ポット総額", value=f"{self.pot:,} 枚", inline=True)
        log_emb.add_field(name="🏛️ コミュニティカード", value=" ".join([f"{c['suit']}`{c['rank']}`" for c in self.community_cards]), inline=True)
        log_emb.add_field(name="🃏 全員の手札公開", value=hands_log_str, inline=False)
        await self.send_game_log(log_emb)
        
        # 📢 ユーザー公開用結果履歴に送信 (対戦ボードと全く同じ見栄えで永続化)
        public_history_emb = discord.Embed(title="📊 ポーカー対戦結果 (ショーダウン)", color=0x9b59b6, timestamp=datetime.datetime.now())
        public_history_emb.add_field(name="🏛️ コミュニティカード (場)", value=" ".join([f"{c['suit']}`{c['rank']}`" for c in self.community_cards]), inline=False)
        public_history_emb.add_field(name="💰 ポット総額", value=f"{self.pot:,} 枚", inline=True)
        public_history_emb.add_field(name="👑 卓作成者", value=host_mention, inline=True)
        public_history_emb.add_field(name="🏆 獲得分配内訳", value=winners_log_str if winners_log_str else "なし", inline=False)
        public_history_emb.add_field(name="🃏 最終手札公開", value=hands_log_str if hands_log_str else "なし", inline=False)
        await self.send_result_history(public_history_emb)
        
        await asyncio.sleep(15)  # 👈 10秒から15秒に延長
        try: await self.message.delete()
        except: pass


class PokerGameActionButton(discord.ui.Button):
    def __init__(self, label, style, action_type, row=None):
        super().__init__(label=label, style=style, row=row)
        self.action_type = action_type

    async def callback(self, i: discord.Interaction):
        view: PokerGameView = self.view
        player = view.players[view.current_turn_idx]
        if i.user.id != player.user.id:
            return await i.response.send_message("❌ あなたの手番ではありません！", ephemeral=True)

        view.action_counter += 1
        if self.action_type == "call":
            diff = view.current_bet - player.bet_in_phase
            if diff > 0: 
                res = view.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
                current_coins = res.data[0].get('coin_count', 0) if res.data else 0
                
                if current_coins < diff:
                    diff = current_coins
                    player.is_all_in = True
                    await i.channel.send(f"🔥 **{i.user.display_name} がコール不足のためオールイン！**")
                elif current_coins == diff:
                    player.is_all_in = True
                    await i.channel.send(f"🔥 **{i.user.display_name} がオールイン！**")

                view.bot.supabase.rpc('update_user_stats', {'u_id': str(i.user.id), 'coin_change': -diff}).execute()
                player.bet_in_phase += diff
                player.total_bet += diff
                view.pot += diff
            await view.next_turn(i)

        elif self.action_type == "raise":
            min_raise_total = view.current_bet + 100
            modal = PokerRaiseModal(view, min_raise_total)
            await i.response.send_modal(modal)

        elif self.action_type == "fold":
            player.is_folded = True
            await i.response.send_message("🃏 フォールドしました。", ephemeral=True)
            await view.next_turn(i)


class PokerPanelLaunchView(View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="ポーカーの卓を立てる", style=discord.ButtonStyle.success, emoji="🃏", custom_id="poker_panel_launch")
    async def launch_poker(self, i: discord.Interaction, b: Button):
        if i.user.id in ACTIVE_HOSTS:
            return await i.response.send_message("❌ あなたは既に別のポーカーの卓を立てて募集中です！", ephemeral=True)

        await i.response.defer(thinking=False)
        entry_bet = 100
        
        res = self.bot.supabase.table("user_coins").select("coin_count").eq("user_id", str(i.user.id)).execute()
        current_coins = res.data[0].get('coin_count', 0) if res.data else 0
        if current_coins < entry_bet:
            return await i.followup.send(f"❌ コインが足りないため卓を立てられません！", ephemeral=True)

        ACTIVE_HOSTS.append(i.user.id)
        view = PokerGameView(self.bot, i.user, entry_bet)
        
        view.message = await i.followup.send(
            content=f"📢 **{i.user.mention} がポーカーの参加者を募集しています！**\n下の「参加する」ボタンを押して集まってください！",
            embed=view.create_main_embed(),
            view=view
        )


class PokerSystem(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot

    @app_commands.command(name="poker_panel", description="【管理者専用】常駐型のポーカー募集パネルを設置します")
    @commands.has_permissions(administrator=True)
    async def spawn_poker_panel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        emb = discord.Embed(
            title="🃏 カジノポーカー (テキサスホールデム) 案内所",
            description="誰でも簡単に本格ポーカーで遊ぶことができます！",
            color=0xe74c3c
        )
        await interaction.channel.send(embed=emb, view=PokerPanelLaunchView(self.bot))
        await interaction.followup.send("✅ ポーカー募集パネルをここに設置したよ！", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id", "") if interaction.data else None
        if not custom_id:
            return

        if custom_id.startswith("pkr_x_") or custom_id == "pkr_in_game_peek":
            my_id_str = str(interaction.user.id)
            user_hand = None

            if custom_id.startswith("pkr_x_"):
                raw_data = custom_id.replace("pkr_x_", "")
                tokens = raw_data.split("_")
                for token in tokens:
                    if token.startswith(f"{my_id_str}-"):
                        try:
                            cards_part = token.split("-")[1]
                            c1_str, c2_str = cards_part.split(".")
                            s1 = CHAR_TO_SUIT.get(c1_str[0], '♠️')
                            r1 = c1_str[1:]
                            s2 = CHAR_TO_SUIT.get(c2_str[0], '♠️')
                            r2 = c2_str[1:]
                            
                            user_hand = [
                                {"suit": s1, "rank": r1, "val": RANK_MAP.get(r1, 2)},
                                {"suit": s2, "rank": r2, "val": RANK_MAP.get(r2, 2)}
                            ]
                        except:
                            pass
                        break

            if not user_hand:
                entry_bet = 100
                dummy_view = PokerGameView(self.bot, interaction.guild.me, entry_bet)
                if interaction.message and interaction.message.embeds:
                    embed = interaction.message.embeds[0]
                    field = next((f for f in embed.fields if f.name == "👥 プレイヤー一覧"), None)
                    if field and "まだ参加者はいません" not in field.value:
                        for line in field.value.split("\n"):
                            if not line.strip(): continue
                            try:
                                name_part = line.split("**")[1]
                                member = discord.utils.get(interaction.guild.members, display_name=name_part)
                                if member:
                                    dummy_view.players.append(PokerPlayer(member))
                            except:
                                pass
                
                for idx, p in enumerate(dummy_view.players):
                    if str(p.user.id) == my_id_str:
                        try:
                            user_hand = [dummy_view.deck[idx * 2], dummy_view.deck[idx * 2 + 1]]
                        except:
                            pass
                        break

            if not user_hand:
                return await interaction.response.send_message("❌ あなたの手札データが見つからないか、ゲームに参加していません。", ephemeral=True)

            h_s = ' '.join([f"{c['suit']}`{c['rank']}`" for c in user_hand])
            await interaction.response.send_message(
                f"🤫 **【あなた専用の手札画面】**\n\n### あなたの手札： {h_s}\n\n※このメッセージは他の人には絶対に見えていません。画面を閉じれば消去されます！", 
                ephemeral=True
            )
            return

        if not custom_id.startswith("pkr_init_"):
            return

        entry_bet = 100
        creator_id = 0
        try:
            creator_id = int(custom_id.split("_")[-1])
        except:
            pass

        dummy_view = PokerGameView(self.bot, interaction.guild.me, entry_bet)
        dummy_view.creator_id = creator_id
        dummy_view.message = interaction.message
        
        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0]
            field = next((f for f in embed.fields if f.name == "👥 プレイヤー一覧"), None)
            if field and "まだ参加者はいません" not in field.value:
                for line in field.value.split("\n"):
                    if not line.strip(): continue
                    try:
                        name_part = line.split("**")[1]
                        member = discord.utils.get(interaction.guild.members, display_name=name_part)
                        if member:
                            dummy_view.players.append(PokerPlayer(member))
                    except:
                        pass

        if custom_id.startswith("pkr_init_join"):
            await dummy_view.handle_global_join(interaction)
        elif custom_id.startswith("pkr_init_start"):
            await dummy_view.handle_global_start(interaction)

async def setup(bot):
    await bot.add_cog(PokerSystem(bot))