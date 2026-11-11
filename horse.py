import random
from .settings import Settings
from .protection import is_negative_buff, positive_buff_parts

class horse:
    def __init__(self, horsename = "the_horse", uid = 114514, id = "the_player", location = 0, round = 0, settings=None ):
        self.settings = settings or Settings()
        self.horse = horsename
        self.playeruid = uid
        self.player =  id
        self.buff = []
        self.delay_events = []
        self.horse_fullname = horsename
        self.round = round
        self.location = location
        self.location_add = 0
        self.location_add_move = 0
        self.negative_immunity = False
        self.blocked_effect_count = 0

    def block_negative(self, harmful: bool) -> bool:
        if harmful and self.negative_immunity:
            self.blocked_effect_count += 1
            return True
        return False

    def grant_negative_immunity(self) -> None:
        self.negative_immunity = True
        purified = []
        for buff in self.buff:
            if is_negative_buff(buff):
                buff = positive_buff_parts(buff)
            if buff is not None:
                purified.append(buff)
        self.buff = purified
# =====替换为其他马,指定马（没用上，暂留）
    def replace_horse(self, horse_to):
        if self.block_negative(True):
            return
        self.horse = horse_to.horse
        self.playeruid = horse_to.playeruid
        self.player = horse_to.player
        self.buff = horse_to.buff
        self.delay_events = horse_to.delay_events
        self.horse_fullname = horse_to.horse_fullname
        self.round = horse_to.round
        self.location = horse_to.location
        self.location_add = horse_to.location_add
        self.location_add_move = horse_to.location_add_move
#=====替换为其他马,指定数据（用于天灾马系列事件）
    def replace_horse_ex(self, horsename="the_horse", uid=114514, id="the_player"):
        if self.block_negative(True):
            return
        self.horse = horsename
        self.playeruid = uid
        self.player = id
        self.buff = []
        self.delay_events = []
        self.horse_fullname = horsename
        self.location_add = 0
        self.location_add_move = 0
#=====马儿buff增加：buff为list格式
    def add_buff(self, buff_name, round_start, round_end, buffs, move_min = 0, move_max = 0, event_in_buff = None):
        if  move_min > move_max:
            move_max = move_min
        buff = [buff_name, round_start, round_end, move_min, move_max, event_in_buff or []]
        buff.extend(buffs)
        if self.block_negative(is_negative_buff(buff)):
            buff = positive_buff_parts(buff)
            if buff is None:
                return
        self.buff.append(buff)
#=====马儿指定buff移除：
    def del_buff(self, del_buff_key):
        for i in range(0, len(self.buff)):
            try:
                if self.buff[i][0] != del_buff_key:
                    self.buff[i].index(del_buff_key, 6)
                if self.block_negative(not is_negative_buff(self.buff[i])):
                    continue
                self.buff[i][2] = self.round
            except ValueError:
                pass
#=====马儿查找有无buff（查参数非名称）：(跳过计算回合数，只查有没有）
    def find_buff(self, find_buff_key):
        if find_buff_key == "negative_immunity":
            return self.negative_immunity
        for i in range(0, len(self.buff)):
            try:
                self.buff[i].index(find_buff_key, 6)
                return True
            except ValueError:
                pass
        return False
#=====马儿超时buff移除：
    def del_buff_overtime(self, round):
        for i in range(len(self.buff) - 1, -1, -1):
            if self.buff[i][2] < round:
                del self.buff[i]
#=====马儿buff时间延长/减少：
    def buff_addtime(self, round_add):
        for i in range(0, len(self.buff)):
            harmful = (round_add < 0 and not is_negative_buff(self.buff[i])) or (round_add > 0 and is_negative_buff(self.buff[i]))
            if self.block_negative(harmful):
                continue
            self.buff[i][2] += round_add
#=====马儿是否止步：
    def is_stop(self) -> bool:
        for i in range(0, len(self.buff)):
            try:
                self.buff[i].index("locate_lock", 6)
                if self.buff[i][1] <= self.round:
                    return True
            except ValueError:
                pass
        return False
#=====马儿是否已经离开：
    def is_away(self) -> bool:
        for i in range(0, len(self.buff)):
            try:
                self.buff[i].index("away", 6)
                if self.buff[i][1] <= self.round:
                    return True
            except ValueError:
                pass
        return False
#=====马儿是否已经死亡：
    def is_die(self) -> bool:
        for i in range(0, len(self.buff)):
            try:
                self.buff[i].index("die", 6)
                if self.buff[i][1] <= self.round:
                    return True
            except ValueError:
                pass
        return False
#=====马儿全名带buff显示：
    def fullname(self):
        fullname = "<不死图腾>" if self.negative_immunity else ""
        for i in range(0, len(self.buff)):
            if self.buff[i][1] <= self.round:
                fullname += ( "<" + self.buff[i][0] + ">" )
        self.horse_fullname = fullname + self.horse
#=====马儿移动计算（事件提供的本回合移动）：
    def location_move_event(self, move):
        if self.block_negative(move < 0):
            return
        self.location_add_move += move
#=====马儿移动至特定位置计算（事件提供移动）：
    def location_move_to_event(self, move_to):
        if self.block_negative(move_to < self.location):
            return
        self.location_add_move += move_to - self.location
#=====马儿移动计算：
    def location_move(self):
        if self.is_die() or self.is_away():
            self.location_add = 0
            self.location_add_move = 0
            return
        if self.location != self.settings.setting_track_length:
            self.location_add = self.move() + self.location_add_move
            self.location += self.location_add
            if self.location > self.settings.setting_track_length:
                self.location_add -= self.location - self.settings.setting_track_length
                self.location = self.settings.setting_track_length
            if self.location < 0:
                self.location_add -= self.location
                self.location = 0
#=====马儿移动量计算：
    def move(self):
        if self.is_stop() == True:
            return 0
        if self.is_die() == True:
            return 0
        if self.is_away() == True:
            return 0
        move_min = 0
        move_max = 0
        for i in range(0, len(self.buff)):
            if self.buff[i][1] <= self.round:
                move_min += self.buff[i][3]
                move_max += self.buff[i][4]
        return random.randint(move_min + self.settings.base_move_min, max(move_min + self.settings.base_move_min, move_max + self.settings.base_move_max))
#=====赛马玩家战况显示：
    def display(self):
        display = f""
        if self.find_buff("hiding") == False:
            if self.location_add < 0:
                display += "[" + str(self.location_add) + "]"
            else:
                display += "[+" + str(self.location_add) + "]"
            for i in range(0, self.settings.setting_track_length - self.location):
                display += "."
            display += self.horse_fullname
            for i in range(self.settings.setting_track_length - self.location, self.settings.setting_track_length):
                display += "."
        else:
            display += "[+？]"
            for i in range(0, self.settings.setting_track_length):
                display += "."
        display += "\n"
        return display
